from flask import Blueprint, render_template, jsonify, request, send_from_directory
from flask_jwt_extended import jwt_required, get_jwt_identity


from App.controllers import (
    create_customer,
    create_staff, 
    get_all_users,
    get_all_users_json,
    get_all_customers_json,
    jwt_authenticate,
    is_staff,
    get_user,
    get_user_by_username
)

user_views = Blueprint('user_views', __name__, template_folder='../templates')


@user_views.route('/signup', methods=['POST'])
def signup():
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        return jsonify({"error": "JSON object required"}), 400
    username = data.get('username')
    password = data.get('password')
    if not isinstance(username, str) or not isinstance(password, str) or not username.strip() or not password:
        return jsonify({"error": "username and password are required"}), 400
    result = create_customer(username=username, password=password)
    if result:
        return jsonify({"message": "account created"}), 201
    if get_user_by_username(username):
        return jsonify({"error": "username already taken"}), 400
    return jsonify({"error": "account not created"}), 500


@user_views.route('/auth', methods=['POST'])
def login():
    data = request.json
    result = jwt_authenticate(data['username'], data['password'])
    if not result:
        return jsonify(error="invalid credentials")
    return jsonify(access_token=result)

@user_views.route('/users', methods=['GET'])
@jwt_required()
def client_app():
    if is_staff(get_jwt_identity()):
        users = get_all_users_json()
        return jsonify(users)
    return jsonify({"error": "User not authorized to perform this action"}), 403


@user_views.route('/customers', methods=['GET'])
@jwt_required()
def customers():
    if is_staff(get_jwt_identity()):
        users = get_all_customers_json()
        return jsonify(users)
    return jsonify({"error": "User not authorized to perform this action"}), 403


@user_views.route('/customer', methods=['POST'])
def create_customer_action():
    data = request.json
    result = create_customer(username=data['username'], password=data['password'])
    if result:
        return jsonify({"message": f"Customer created with id {result.id}"}), 201
    return jsonify({"error": f"Username {data['username']} already exists "}), 500

@user_views.route('/staff', methods=['POST'])
def create_staff_action():
    data = request.json
    result = create_staff(username=data['username'], password=data['password'])
    if result:
        return jsonify({"message": f"Staff created with id {result.id}"}), 201
    return jsonify({"error": f"Username {data['username']} already exists "}), 500

@user_views.route('/identify', methods=['GET'])
@jwt_required()
def identify_user_action():
    current_identity = get_user(get_jwt_identity())
    return jsonify({'message': f"username: {current_identity.username}, id : {get_jwt_identity()}, type: {current_identity.user_type}"})