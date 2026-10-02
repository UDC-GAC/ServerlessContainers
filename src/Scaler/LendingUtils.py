# Resources that can be lent by idle containers
LENDABLE_RESOURCES = {"cpu", "mem", "disk_read", "disk_write"}

FREE_KEY = "free"
LENT_KEY = "lent"
LENT_MAPPING_KEY = "lent_mapping"


def get_pool(host_info, resource, bound_disk=None):
    """Get the host dictionary holding the lent pool of a resource and the keys used for the pool and its mapping

    Args:
        host_info (dict): Host structure
        resource (string): Resource name (e.g., cpu)
        bound_disk (string): Name of the disk bound to the container, only needed for disk resources

    Returns:
        (tuple[dict,string,string]) Dictionary holding the pool, key of the available lent amount and key of the mapping
    """
    if resource in {"disk_read", "disk_write"}:
        disk_op = resource.split("_")[-1]
        return host_info["resources"]["disks"][bound_disk], "{0}_{1}".format(LENT_KEY, disk_op), "{0}_{1}".format(LENT_MAPPING_KEY, disk_op)
    return host_info["resources"][resource], LENT_KEY, LENT_MAPPING_KEY


def _get_slots(resource, lender_entry):
    """Get the slots of a lender as (slot_id, slot) tuples. CPU shares are lent per core (slot_id is the core), the
    rest of resources are lent as a single slot (slot_id is None)"""
    if resource == "cpu":
        return list(lender_entry.items())
    return [(None, lender_entry)] if lender_entry else []


def _get_slot(pool, mapping_key, resource, lender, slot_id):
    lender_entry = pool[mapping_key][lender]
    return lender_entry[slot_id] if resource == "cpu" else lender_entry


def _move(slot, from_key, to_key, amount):
    slot[from_key] = slot.get(from_key, 0) - amount
    slot[to_key] = slot.get(to_key, 0) + amount


def get_available(host_info, resource, borrower, bound_disk=None):
    """Get the amount of lent resources that a container can borrow (a container can't borrow its own resources)"""
    pool, lent_key, mapping_key = get_pool(host_info, resource, bound_disk)
    own_entry = pool.get(mapping_key, {}).get(borrower, {})
    own_available = sum(slot.get(FREE_KEY, 0) for _, slot in _get_slots(resource, own_entry))
    return pool.get(lent_key, 0) - own_available


def get_borrowed(host_info, resource, borrower, bound_disk=None):
    """Get the resources borrowed by a container as {slot_id: amount}, where slot_id is the core for cpu, else None"""
    pool, _, mapping_key = get_pool(host_info, resource, bound_disk)
    borrowed = {}
    for lender_entry in pool.get(mapping_key, {}).values():
        for slot_id, slot in _get_slots(resource, lender_entry):
            if slot.get(borrower, 0) > 0:
                borrowed[slot_id] = borrowed.get(slot_id, 0) + slot[borrower]
    return borrowed

def get_borrowers(host_info, resource, lender, bound_disk=None):
    """Get the resources borrowed from a lender as {borrower: amount}"""
    pool, _, mapping_key = get_pool(host_info, resource, bound_disk)
    borrowers = {}
    for _, slot in _get_slots(resource, pool.get(mapping_key, {}).get(lender, {})):
        for key, value in slot.items():
            if key != FREE_KEY and value > 0:
                borrowers[key] = borrowers.get(key, 0) + value
    return borrowers

def lend(host_info, resource, lender, amount, bound_disk=None):
    """Add the current allocation of an idle container to the lent pool of its host. The container keeps its
    allocation, but other containers can borrow it when scaling up.

    Raises:
        ValueError if the container is borrowing resources, it is already lending or its allocation is inconsistent
    """
    pool, lent_key, mapping_key = get_pool(host_info, resource, bound_disk)
    mapping = pool.setdefault(mapping_key, {})

    if get_borrowed(host_info, resource, lender, bound_disk):
        raise ValueError("Container {0} is using borrowed {1}, it can't lend it".format(lender, resource))

    if any(value for _, slot in _get_slots(resource, mapping.get(lender, {})) for value in slot.values()):
        raise ValueError("Container {0} is already lending {1}".format(lender, resource))

    if resource == "cpu":
        # Shares are bound to cores, so they are lent in the same cores where they are mapped
        own_shares = {core: usages[lender] for core, usages in pool["core_usage_mapping"].items() if usages.get(lender, 0) > 0}
        if sum(own_shares.values()) != amount:
            raise ValueError("Container {0} has {1} shares mapped in the host cores, but {2} shares were going to be lent"
                             .format(lender, sum(own_shares.values()), amount))
        mapping[lender] = {core: {FREE_KEY: shares} for core, shares in own_shares.items()}
    else:
        mapping[lender] = {FREE_KEY: amount}

    pool[lent_key] = pool.get(lent_key, 0) + amount


def cancel_lend(host_info, resource, lender, bound_disk=None):
    """End a lending whose resources are not borrowed (e.g., the lending could not be persisted or it has been
    reclaimed). Lender entries are set to zero instead of being removed, as host changes are persisted as differences"""
    pool, lent_key, mapping_key = get_pool(host_info, resource, bound_disk)
    slots = _get_slots(resource, pool.get(mapping_key, {}).get(lender, {}))
    if any(key != FREE_KEY and value for _, slot in slots for key, value in slot.items()):
        raise ValueError("{0} lent by container {1} is already borrowed, lending can't be cancelled".format(resource, lender))
    for _, slot in slots:
        pool[lent_key] = pool.get(lent_key, 0) - slot.get(FREE_KEY, 0)
        for key in slot:
            slot[key] = 0

def borrow(host_info, resource, borrower, amount, journal, bound_disk=None, preferred_slots=None):
    """Borrow up to 'amount' of the resources lent by other containers in the host

    Args:
        host_info (dict): Host structure
        resource (string): Resource name (e.g., cpu)
        borrower (string): Name of the container borrowing the resources
        amount (integer): Amount to borrow
        journal (list): List where movements are registered so that they can be reverted
        bound_disk (string): Name of the disk bound to the container, only needed for disk resources
        preferred_slots (list): Slots (i.e., cores) to be used first, following the list order

    Returns:
        (tuple[int,list]) Borrowed amount and slots from which it has been borrowed
    """
    pool, lent_key, mapping_key = get_pool(host_info, resource, bound_disk)
    candidates = []
    for lender, lender_entry in pool.get(mapping_key, {}).items():
        if lender == borrower:
            continue
        for slot_id, slot in _get_slots(resource, lender_entry):
            if slot.get(FREE_KEY, 0) > 0:
                candidates.append((lender, slot_id, slot))

    if preferred_slots:
        order = {slot_id: i for i, slot_id in enumerate(preferred_slots)}
        candidates.sort(key=lambda c: order.get(c[1], len(order)))

    borrowed, borrowed_slots = 0, []
    for lender, slot_id, slot in candidates:
        if borrowed >= amount:
            break
        take = min(slot[FREE_KEY], amount - borrowed)
        _move(slot, FREE_KEY, borrower, take)
        journal.append((lender, slot_id, FREE_KEY, borrower, take))
        borrowed += take
        if slot_id not in borrowed_slots:
            borrowed_slots.append(slot_id)

    pool[lent_key] = pool.get(lent_key, 0) - borrowed
    return borrowed, borrowed_slots


def release(host_info, resource, borrower, amount, journal, bound_disk=None, lenders=None):
    """Give back up to 'amount' of the resources borrowed by a container to the lent pool

    Args:
        lenders (list): If set, only the resources borrowed from these lenders are given back

    Returns:
        (int) Released amount
    """
    pool, lent_key, mapping_key = get_pool(host_info, resource, bound_disk)
    released = 0
    for lender, lender_entry in pool.get(mapping_key, {}).items():
        if lenders is not None and lender not in lenders:
            continue
        for slot_id, slot in _get_slots(resource, lender_entry):
            take = min(slot.get(borrower, 0), amount - released)
            if take > 0:
                _move(slot, borrower, FREE_KEY, take)
                journal.append((lender, slot_id, borrower, FREE_KEY, take))
                released += take

    pool[lent_key] = pool.get(lent_key, 0) + released
    return released


def revert(host_info, resource, journal, bound_disk=None):
    """Revert the movements registered in a journal by borrow/release"""
    pool, lent_key, mapping_key = get_pool(host_info, resource, bound_disk)
    for lender, slot_id, from_key, to_key, amount in reversed(journal):
        _move(_get_slot(pool, mapping_key, resource, lender, slot_id), to_key, from_key, amount)
        # Borrowed resources return to the lent pool, released resources are taken from it again
        pool[lent_key] += amount if from_key == FREE_KEY else -amount
    journal.clear()


def record_changes(host_changes, host_name, host_info, resource, bound_disk=None):
    """Register the current state of the lent pool of a resource in the host changes that will be persisted"""
    pool, lent_key, mapping_key = get_pool(host_info, resource, bound_disk)
    resource_changes = host_changes.setdefault(host_name, {}).setdefault("resources", {})
    if resource in {"disk_read", "disk_write"}:
        resource_changes = resource_changes.setdefault("disks", {}).setdefault(bound_disk, {})
    else:
        resource_changes = resource_changes.setdefault(resource, {})
    resource_changes[lent_key] = pool.get(lent_key, 0)
    resource_changes[mapping_key] = pool.get(mapping_key, {})


def settle_unsubscribed_container(host_info, resource, container_name, bound_disk=None):
    """Settle the lent pool of a resource when a container is unsubscribed from its host:

    * Resources borrowed by the container are given back to the lent pool of their lenders
    * Resources lent by the container that are not borrowed are removed from the lent pool, as they return to the
      'free' pool along with the rest of the container allocation
    * Resources lent by the container that are borrowed by other containers become owned by these containers. For cpu,
      the shares are moved from the container to the borrowers in the host core usage mapping

    Lender entries are set to zero instead of being removed, as host changes are persisted as differences.

    Returns:
        (int) Amount of the container allocation that must not be returned to the 'free' pool, i.e., resources borrowed
        by the container plus resources lent by the container that now belong to other containers. For cpu it is only
        informative, as the core usage mapping is already updated (borrowed shares are not in the core usage mapping).
    """
    pool, lent_key, mapping_key = get_pool(host_info, resource, bound_disk)

    # 1) Give back the resources borrowed by the container to the lent pool of their lenders
    borrowed = sum(get_borrowed(host_info, resource, container_name, bound_disk).values())
    if borrowed > 0:
        release(host_info, resource, container_name, borrowed, [], bound_disk)

    # 2) Settle the resources lent by the container
    transferred = 0
    for slot_id, slot in _get_slots(resource, pool.get(mapping_key, {}).get(container_name, {})):
        for key, value in slot.items():
            if value == 0:
                continue
            if key == FREE_KEY:
                # Not borrowed resources are no longer lendable
                pool[lent_key] = pool.get(lent_key, 0) - value
            else:
                # Borrowed resources become owned by their borrowers
                transferred += value
                if resource == "cpu":
                    core_usage = pool["core_usage_mapping"][slot_id]
                    core_usage[container_name] = core_usage.get(container_name, 0) - value
                    core_usage[key] = core_usage.get(key, 0) + value
            slot[key] = 0

    return borrowed + transferred