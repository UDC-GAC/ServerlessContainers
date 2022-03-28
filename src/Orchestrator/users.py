from flask import Blueprint
from flask import abort
from flask import jsonify
from flask import request
import time


from src.Orchestrator.utils import BACK_OFF_TIME_MS, MAX_TRIES, get_db

users_routes = Blueprint('users', __name__)

@users_routes.route("/user/", methods=['GET'])
def get_users():
    return jsonify(get_db().get_users())


@users_routes.route("/user/<user_name>", methods=['GET'])
def get_user(user_name):
    return jsonify(get_db().get_user(user_name))


@users_routes.route("/user/<user_name>/energy/max", methods=['PUT'])
def set_user_energy_max(user_name):
    user = get_db().get_user(user_name)
    try:
        bogus = user["energy"]["max"]
    except KeyError:
        abort(404)

    value = int(request.json["value"])
    if value < 0:
        return abort(400)

    put_done = False
    tries = 0
    while not put_done:
        tries += 1
        user["energy"]["max"] = value
        get_db().update_user(user)

        time.sleep(BACK_OFF_TIME_MS / 1000)
        user = get_db().get_user(user_name)
        put_done = user["energy"]["max"] == value

        if tries >= MAX_TRIES:
            return abort(400, {"message": "MAX_TRIES updating database document"})

    return jsonify(201)