import os, tempfile, pytest, logging, unittest
from datetime import datetime, timedelta
from werkzeug.security import check_password_hash, generate_password_hash

import App.controllers.user as user_controller
from App.main import create_app
from App.database import create_db, db
from App.models import User, Staff, RentalPayment, Payment
from App.controllers import (
    create_user,
    create_customer,
    create_game,
    get_customer,
    create_staff,
    get_all_users_json,
    authenticate,
    get_staff,
    get_game,
    get_rental,
    get_user,
    get_listing,
    create_rental,
    create_rental_payment
)

app = create_app({"SQLALCHEMY_DATABASE_URI":'sqlite:///:memory:', "TESTING":True, "DEBUG":True})


LOGGER = logging.getLogger(__name__)

'''
   Unit Tests
'''
class UserUnitTests(unittest.TestCase):

    def test_new_user(self):
        user = Staff("bob", "bobpass")
        assert user.username == "bob"

    def test_toJSON(self):
        user = Staff("bob", "bobpass")
        user_json = user.toJSON()
        self.assertDictEqual(user_json, {"id":None, "username":"bob", "type": 'staff'})
    
    # def test_hashed_password(self):

    # def test_check_password(self):
        

'''
    Integration Tests
'''

# Each test starts with empty tables in an isolated in-memory database.
@pytest.fixture(autouse=True)
def empty_db(monkeypatch):
    # These integration tests must not contact RAWG or any other HTTP API.
    monkeypatch.delattr('requests.sessions.Session.request')
    with app.app_context():
        create_db(app)
        try:
            yield
        finally:
            db.session.remove()
            db.drop_all()


@pytest.fixture
def listed_game():
    staff = create_staff('bob', 'bobpass')
    owner = create_customer('rob', 'robpass')
    renter = create_customer('jane', 'janepass')
    game = create_game('Frogger', rawgId=123, platform='PS5')
    assert staff is not None
    assert owner is not None
    assert renter is not None
    listing = staff.list_game(owner, game, 'good', 20.00)
    assert listing is not None
    return staff.id, owner.id, renter.id, game.gameId, listing.listingId


def test_create_user():
    user = create_user('alex', 'alexpass')
    assert user is not None
    user_id = user.id
    assert user_id is not None
    db.session.remove()

    saved = get_user(user_id)
    assert saved is not None
    assert saved.id == user_id
    assert saved.username == 'alex'
    assert saved.password != 'alexpass'
    assert saved.check_password('alexpass')
    assert not saved.check_password('wrongpass')
    assert User.query.count() == 1


def test_authenticate():
    user = create_user('alex', 'alexpass')
    staff = create_staff('bob', 'bobpass')
    customer = create_customer('rob', 'robpass')
    assert user is not None
    assert staff is not None
    assert customer is not None
    user_id, staff_id, customer_id = user.id, staff.id, customer.id
    db.session.remove()

    assert authenticate('missing', 'alexpass') is None
    assert authenticate('alex', 'wrongpass') is None
    assert authenticate('bob', 'wrongpass') is None
    assert authenticate('rob', 'wrongpass') is None
    assert authenticate('bob', 'bobpass').id == staff_id
    assert authenticate('rob', 'robpass').id == customer_id
    authenticated = authenticate('alex', 'alexpass')
    assert authenticated is not None, 'authenticate() must accept a user created by create_user()'
    assert authenticated.id == user_id


def test_get_all_users_json():
    assert get_all_users_json() == []
    user = create_user('alex', 'alexpass')
    staff = create_staff('bob', 'bobpass')
    customer = create_customer('rob', 'robpass')
    assert user is not None
    assert staff is not None
    assert customer is not None
    expected = [
        {'id': user.id, 'username': 'alex'},
        {'id': staff.id, 'username': 'bob', 'type': 'staff'},
        {'id': customer.id, 'username': 'rob', 'type': 'customer', 'status': 'active'}
    ]
    db.session.remove()

    users_json = get_all_users_json()
    assert sorted(users_json, key=lambda user: user['id']) == expected


def test_update_user():
    user = create_user('alex', 'alexpass')
    assert user is not None
    user_id = user.id
    # Keep the tutorial's generic-user requirement visible if the function is missing.
    update_user = getattr(user_controller, 'update_user', None)
    assert callable(update_user), 'The tutorial requires update_user(), but only update_staff() exists'
    update_user(user_id, 'alex_updated')
    db.session.remove()

    saved = get_user(user_id)
    assert saved is not None
    assert saved.id == user_id
    assert saved.username == 'alex_updated'
    assert saved.check_password('alexpass')
    assert User.query.count() == 1


def test_staff_create_listing(listed_game):
    staff_id, owner_id, renter_id, game_id, listing_id = listed_game
    db.session.remove()

    listing = get_listing(listing_id)
    assert listing is not None
    assert listing.listingId == listing_id
    assert listing.ownerId == owner_id
    assert listing.gameId == game_id
    assert listing.owner.id == owner_id
    assert listing.game.gameId == game_id
    assert listing in get_customer(owner_id).listings
    assert listing in get_game(game_id).listings
    assert listing.condition == 'good'
    assert listing.price == pytest.approx(20.00)
    assert listing.status == 'available'
    assert listing.created is not None
    # Page 1 also requires the listing to record the corresponding staff ID.
    assert getattr(listing, 'staffId', None) == staff_id, 'Listing does not record the staff member who created it'


def test_staff_confirm_rental(listed_game):
    staff_id, owner_id, renter_id, game_id, listing_id = listed_game
    rental = get_staff(staff_id).confirm_rental(get_user(renter_id), get_listing(listing_id))
    assert rental is not None
    rental_id = rental.rentalId
    assert rental_id is not None
    db.session.remove()

    saved = get_rental(rental_id)
    assert saved is not None
    assert saved.renterId == renter_id
    assert saved.listingId == listing_id
    assert saved.renter.id == renter_id
    assert saved.listing.ownerId == owner_id
    assert saved.listing.gameId == game_id
    assert saved in get_customer(renter_id).rentals
    assert saved in get_listing(listing_id).rentals
    assert saved.rental_date is not None
    assert saved.return_date is None
    assert Payment.query.count() == 1
    payment = RentalPayment.query.one()
    assert payment.paymentId is not None
    assert payment.customerId == renter_id
    assert payment.amount == pytest.approx(20.00)
    assert payment.payment_date is not None
    assert payment.paymentId in [item.paymentId for item in get_customer(renter_id).payments]
    # Check both requirements together so pytest exposes both discrepancies.
    assert {
        'payment_rentalId': payment.rentalId,
        'rental_payment_ids': [item.paymentId for item in saved.payments],
        'listing_status': get_listing(listing_id).status
    } == {
        'payment_rentalId': rental_id,
        'rental_payment_ids': [payment.paymentId],
        'listing_status': 'rented'
    }


@pytest.mark.parametrize('days_rented, expected_fees', [(7, 0.00), (17, 6.00)])
def test_staff_return_rental(listed_game, days_rented, expected_fees):
    staff_id, owner_id, renter_id, game_id, listing_id = listed_game
    # Seed a committed rental and its original payment independently of confirm_rental().
    rental = create_rental(renter_id, listing_id)
    assert rental is not False
    rental.rental_date = datetime.utcnow() - timedelta(days=days_rented)
    db.session.commit()
    payment = create_rental_payment(rental)
    rental_id, original_payment_id = rental.rentalId, payment.paymentId
    assert rental.return_date is None
    assert get_listing(listing_id).status == 'rented'
    assert Payment.query.count() == 1
    db.session.remove()

    before_return = datetime.utcnow()
    fees = get_staff(staff_id).confirm_return(get_rental(rental_id))
    after_return = datetime.utcnow()
    assert fees is not None
    assert fees == pytest.approx(expected_fees)
    db.session.remove()

    saved = get_rental(rental_id)
    assert before_return <= saved.return_date <= after_return
    assert saved.renterId == renter_id
    assert saved.listingId == listing_id
    assert saved.renter.id == renter_id
    assert saved.listing.listingId == listing_id
    assert get_listing(listing_id).status == 'available'
    original_payment = RentalPayment.query.get(original_payment_id)
    assert original_payment.rentalId == rental_id
    assert original_payment.amount == pytest.approx(20.00)

    new_payments = RentalPayment.query.filter(RentalPayment.paymentId != original_payment_id).all()
    for new_payment in new_payments:
        assert new_payment.rentalId == rental_id
        assert new_payment.customerId == renter_id
        assert before_return <= new_payment.payment_date <= after_return
        assert new_payment in saved.payments
        assert new_payment.paymentId in [item.paymentId for item in get_customer(renter_id).payments]
    expected_amounts = [expected_fees] if expected_fees > 0 else []
    assert {
        'total_payments': Payment.query.count(),
        'return_payment_amounts': [item.amount for item in new_payments]
    } == {
        'total_payments': 1 + len(expected_amounts),
        'return_payment_amounts': expected_amounts
    }


'''
    API Tests
'''

def test_signup_success():
    response = app.test_client().post('/signup', json={'username': 'alex', 'password': 'alexpass'})
    assert response.status_code == 201
    assert response.get_json() == {'message': 'account created'}
    db.session.remove()

    user = user_controller.get_user_by_username('alex')
    assert user is not None
    assert user.id is not None
    assert user.user_type == 'customer'
    assert get_customer(user.id) is not None
    assert user.password != 'alexpass'
    assert user.check_password('alexpass')
    assert authenticate('alex', 'alexpass').id == user.id
    assert User.query.count() == 1


@pytest.mark.parametrize('create_account', [create_user, create_staff, create_customer])
def test_signup_duplicate_username(create_account):
    original = create_account('alex', 'originalpass')
    assert original is not None
    original_id, original_password = original.id, original.password

    response = app.test_client().post('/signup', json={'username': 'alex', 'password': 'newpass'})
    assert response.status_code == 400
    assert response.get_json() == {'error': 'username already taken'}
    db.session.remove()

    user = get_user(original_id)
    assert user.username == 'alex'
    assert user.password == original_password
    assert user.check_password('originalpass')
    assert not user.check_password('newpass')
    assert User.query.count() == 1


@pytest.mark.parametrize('data', [
    {},
    {'username': 'alex'},
    {'password': 'alexpass'},
    {'username': '', 'password': 'alexpass'},
    {'username': 'alex', 'password': ''},
    {'username': None, 'password': 'alexpass'},
    {'username': 'alex', 'password': None},
    {'username': 123, 'password': 'alexpass'},
    {'username': 'alex', 'password': 123}
])
def test_signup_invalid_fields(data):
    response = app.test_client().post('/signup', json=data)
    assert response.status_code == 400
    assert response.get_json() == {'error': 'username and password are required'}
    assert User.query.count() == 0


@pytest.mark.parametrize('body', ['', '{', '[]', 'null'])
def test_signup_invalid_json(body):
    response = app.test_client().post('/signup', data=body, content_type='application/json')
    assert response.status_code == 400
    assert response.get_json() == {'error': 'JSON object required'}
    assert User.query.count() == 0
