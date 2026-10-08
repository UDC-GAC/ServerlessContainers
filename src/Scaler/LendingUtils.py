# Resources that can be lent by idle containers
LENDABLE_RESOURCES = {"cpu", "mem", "disk_read", "disk_write"}
DISK_RESOURCES = {"disk_read", "disk_write"}

# Separator used in the borrower keys of containers using idle bandwidth of the opposite disk operation
CROSS_KEY_SEPARATOR = "@"

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

def get_opposite_disk_resource(resource):
    return "disk_write" if resource == "disk_read" else "disk_read"


def cross_borrower_key(borrower, resource):
    """Key that identifies, in the lent pool of the opposite disk operation, a container that uses that idle bandwidth
    to scale up 'resource' (e.g., 'cont1@disk_write' in the disk_read lent pool)"""
    return "{0}{1}{2}".format(borrower, CROSS_KEY_SEPARATOR, resource)


def parse_borrower_key(key, resource):
    """Get the container and the resource it scales up from a borrower key found in the lent pool of 'resource'"""
    if CROSS_KEY_SEPARATOR in key:
        borrower, borrowed_resource = key.split(CROSS_KEY_SEPARATOR, 1)
        return borrower, borrowed_resource
    return key, resource


def get_cross_borrowed(host_info, resource, borrower, bound_disk):
    """Get the idle bandwidth of the opposite disk operation used by a container to scale up 'resource'"""
    return get_borrowed(host_info, get_opposite_disk_resource(resource), cross_borrower_key(borrower, resource), bound_disk)


def get_disk_capacity(host_info, resource, container_name, bound_disk):
    """Get how much a container can scale up a disk resource, split by source:

    * Free bandwidth, limited by the free bandwidth of the operation and the total free bandwidth of the disk
    * Bandwidth lent by idle containers for the same operation
    * Free bandwidth of the operation that can't be used due to the total bandwidth limit, as long as the bandwidth
      of the opposite operation is idle (i.e., lent). The bandwidth lent by the container itself can also be used,
      as it means that its opposite operation is idle

    Returns:
        (tuple[int,int,int]) Free bandwidth, bandwidth lent for the same operation and bandwidth of the operation that
        can be used thanks to the idle bandwidth of the opposite operation
    """
    disk = host_info["resources"]["disks"][bound_disk]
    op_free = disk["free_{0}".format(resource.split("_")[-1])]
    consumed = (disk["max_read"] - disk["free_read"]) + (disk["max_write"] - disk["free_write"])
    total_free = max(disk["max_read"], disk["max_write"]) - consumed

    from_free = max(min(op_free, total_free), 0)
    same_op = get_available(host_info, resource, container_name, bound_disk)
    opposite_pool, opposite_lent_key, _ = get_pool(host_info, get_opposite_disk_resource(resource), bound_disk)
    cross_op = max(min(op_free - from_free, opposite_pool.get(opposite_lent_key, 0)), 0)
    return from_free, same_op, cross_op

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

    if resource in DISK_RESOURCES and get_cross_borrowed(host_info, resource, lender, bound_disk):
        raise ValueError("Container {0} is using idle {1} bandwidth for {2}, it can't lend it".format(
            lender, get_opposite_disk_resource(resource), resource))

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

def borrow_cross(host_info, resource, borrower, amount, journal, bound_disk):
    """Use the idle bandwidth lent for the opposite disk operation to scale up a disk resource over the total bandwidth
    of the disk. The amount must be already limited by the free bandwidth of the operation, as it is also taken from it

    Returns:
        (int) Borrowed amount
    """
    borrowed, _ = borrow(host_info, get_opposite_disk_resource(resource), cross_borrower_key(borrower, resource), amount, journal, bound_disk)
    return borrowed


def release_cross(host_info, resource, borrower, amount, journal, bound_disk, lenders=None):
    """Give back up to 'amount' of the idle bandwidth of the opposite disk operation used to scale up a disk resource

    Returns:
        (int) Released amount
    """
    return release(host_info, get_opposite_disk_resource(resource), cross_borrower_key(borrower, resource), amount, journal, bound_disk, lenders)

def apply_disk_scaling(host_info, resource, container_name, amount, bound_disk, lent_journal, cross_journal, reclaim_from=None, reclaim_resource=None):
    """Update the free and lent bandwidth of a disk when a container scales a disk resource:

    * Scale-ups take first the free bandwidth, then the bandwidth lent for the same operation and, lastly, the free
      bandwidth of the operation over the total bandwidth thanks to the idle bandwidth of the opposite operation
    * Scale-downs give back first the idle bandwidth of the opposite operation, then the bandwidth borrowed for the
      same operation and, lastly, the own bandwidth. When reclaiming, only the bandwidth borrowed from a specific
      lender and pool (same or opposite operation) is given back

    It is used both when planning and when executing requests, so that both phases see the same disk state.

    Returns:
        (tuple[int,int]) Final scaled amount and amount taken from (positive) or given back to (negative) the 'free' pool
    """
    opposite_resource = get_opposite_disk_resource(resource)
    disk_info = host_info["resources"]["disks"][bound_disk]
    free_key = "free_{0}".format(resource.split("_")[-1])
    borrowed, released = 0, 0

    if amount > 0:
        from_free = min(amount, get_disk_capacity(host_info, resource, container_name, bound_disk)[0])
        borrowed, _ = borrow(host_info, resource, container_name, amount - from_free, lent_journal, bound_disk)
        cross_amount = min(amount - from_free - borrowed, max(disk_info[free_key] - from_free, 0))
        cross_borrowed = borrow_cross(host_info, resource, container_name, cross_amount, cross_journal, bound_disk)
        amount = from_free + borrowed + cross_borrowed
    elif amount < 0:
        lenders = [reclaim_from] if reclaim_from else None
        reclaim_resource = reclaim_resource or resource
        to_release = abs(amount)
        if not reclaim_from or reclaim_resource == opposite_resource:
            to_release -= release_cross(host_info, resource, container_name, to_release, cross_journal, bound_disk, lenders)
        if not reclaim_from or reclaim_resource == resource:
            released = release(host_info, resource, container_name, to_release, lent_journal, bound_disk, lenders=lenders)

    # Only bandwidth borrowed for the same operation doesn't come from (or return to) the 'free' pool, as the
    # bandwidth used thanks to the idle opposite operation is also taken from the free bandwidth of the operation
    free_amount = amount - borrowed + released
    disk_info[free_key] -= free_amount
    return amount, free_amount

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

    # Idle bandwidth of the opposite operation is given back too, but the bandwidth scaled with it was taken from the
    # 'free' pool of the operation, so it returns to it along with the rest of the container allocation
    if resource in DISK_RESOURCES:
        cross_borrowed = sum(get_cross_borrowed(host_info, resource, container_name, bound_disk).values())
        if cross_borrowed > 0:
            release_cross(host_info, resource, container_name, cross_borrowed, [], bound_disk)

    # 2) Settle the resources lent by the container
    transferred = 0
    for slot_id, slot in _get_slots(resource, pool.get(mapping_key, {}).get(container_name, {})):
        for key, value in slot.items():
            if value == 0:
                continue
            if key == FREE_KEY:
                # Not borrowed resources are no longer lendable
                pool[lent_key] = pool.get(lent_key, 0) - value
            elif CROSS_KEY_SEPARATOR in key:
                # Containers using this idle bandwidth for the opposite operation keep the bandwidth taken from its
                # 'free' pool, as the bandwidth lent by the container is fully returned to the 'free' pool
                pass
            else:
                # Borrowed resources become owned by their borrowers
                transferred += value
                if resource == "cpu":
                    core_usage = pool["core_usage_mapping"][slot_id]
                    core_usage[container_name] = core_usage.get(container_name, 0) - value
                    core_usage[key] = core_usage.get(key, 0) + value
            slot[key] = 0

    return borrowed + transferred