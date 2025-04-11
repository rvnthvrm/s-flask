from flask import Flask, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, or_
from datetime import datetime

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///example.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

# ----------------- MODELS -----------------
class Person(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    age = db.Column(db.Integer)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    addresses = db.relationship('Address', backref='person', lazy=True)
    phones = db.relationship('Phone', backref='person', lazy=True)

class Address(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    street = db.Column(db.String(100))
    city = db.Column(db.String(50))
    person_id = db.Column(db.Integer, db.ForeignKey('person.id'))

class Phone(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    number = db.Column(db.String(20))
    type = db.Column(db.String(10))  # 'home', 'work', etc.
    person_id = db.Column(db.Integer, db.ForeignKey('person.id'))

# ----------------- HELPER FUNCTIONS -----------------
def parse_value(value, col_type):
    """Convert query string values to appropriate Python types"""
    try:
        if isinstance(col_type, db.DateTime):
            return datetime.fromisoformat(value)
        elif isinstance(col_type, db.Integer):
            return int(value)
        elif isinstance(col_type, db.Float):
            return float(value)
        elif isinstance(col_type, db.Boolean):
            return value.lower() in ['true', '1', 'yes']
        return value
    except ValueError:
        return value  # Return as string if conversion fails

def build_filters(model, filters):
    """Build SQLAlchemy filters from query parameters"""
    query_filters = []
    inspector = inspect(model)
    
    for key, value in filters.items():
        if '__' in key:
            # Handle relationships (e.g., 'address__city')
            rel_name, rel_field = key.split('__', 1)
            relationship = getattr(model, rel_name, None)
            if relationship and hasattr(relationship.property.mapper.class_, rel_field):
                rel_model = relationship.property.mapper.class_
                rel_col = getattr(rel_model, rel_field)
                query_filters.append(rel_col.ilike(f'%{value}%') if isinstance(rel_col.type, db.String) else rel_col == value)
        else:
            # Handle direct attributes
            column = inspector.columns.get(key)
            if column:
                col_type = column.type
                parsed_value = parse_value(value, col_type)
                if isinstance(col_type, db.String):
                    query_filters.append(getattr(model, key).ilike(f'%{parsed_value}%'))
                else:
                    query_filters.append(getattr(model, key) == parsed_value)
    return query_filters

def build_query(model):
    """Build filtered and paginated query"""
    # Get all query parameters
    filters = request.args.to_dict()
    
    # Remove special parameters
    page = int(filters.pop('page', 1))
    per_page = int(filters.pop('per_page', 10))
    sort = filters.pop('sort', None)
    search = filters.pop('search', None)
    
    # Base query
    query = model.query
    
    # Apply search across all string fields
    if search:
        search_filters = []
        for column in inspect(model).columns:
            if isinstance(column.type, db.String):
                search_filters.append(getattr(model, column.name).ilike(f'%{search}%'))
        query = query.filter(or_(*search_filters))
    
    # Apply filters
    query_filters = build_filters(model, filters)
    if query_filters:
        query = query.filter(*query_filters)
    
    # Apply sorting
    if sort:
        sort_fields = []
        for field in sort.split(','):
            if field.startswith('-'):
                sort_fields.append(getattr(model, field[1:]).desc())
            else:
                sort_fields.append(getattr(model, field))
        query = query.order_by(*sort_fields)
    
    # Pagination
    paginated_query = query.paginate(page=page, per_page=per_page, error_out=False)
    
    return paginated_query

# ----------------- API ENDPOINTS -----------------
@app.route('/api/persons', methods=['GET'])
def get_persons():
    paginated_persons = build_query(Person)
    return jsonify({
        'data': [{
            'id': p.id,
            'name': p.name,
            'age': p.age,
            'addresses': [{'street': a.street, 'city': a.city} for a in p.addresses],
            'phones': [{'number': ph.number, 'type': ph.type} for ph in p.phones]
        } for p in paginated_persons.items],
        'total': paginated_persons.total,
        'page': paginated_persons.page,
        'per_page': paginated_persons.per_page
    })

@app.route('/api/addresses', methods=['GET'])
def get_addresses():
    paginated_addresses = build_query(Address)
    return jsonify({
        'data': [{
            'id': a.id,
            'street': a.street,
            'city': a.city,
            'person_id': a.person_id
        } for a in paginated_addresses.items],
        'total': paginated_addresses.total,
        'page': paginated_addresses.page,
        'per_page': paginated_addresses.per_page
    })

@app.route('/api/phones', methods=['GET'])
def get_phones():
    paginated_phones = build_query(Phone)
    return jsonify({
        'data': [{
            'id': ph.id,
            'number': ph.number,
            'type': ph.type,
            'person_id': ph.person_id
        } for ph in paginated_phones.items],
        'total': paginated_phones.total,
        'page': paginated_phones.page,
        'per_page': paginated_phones.per_page
    })

# ----------------- HELPER FUNCTIONS -----------------
def validate_required_fields(data, required_fields):
    """Validate required fields in request data"""
    missing = [field for field in required_fields if field not in data]
    if missing:
        raise ValueError(f"Missing required fields: {', '.join(missing)}")

def handle_db_operations():
    """Handle database commit with error handling"""
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        raise e

# ----------------- PERSON ENDPOINTS -----------------
@app.route('/api/persons', methods=['POST'])
def create_person():
    try:
        data = request.get_json()
        validate_required_fields(data, ['name', 'age'])
        
        new_person = Person(
            name=data['name'],
            age=data['age']
        )
        db.session.add(new_person)
        handle_db_operations()
        
        return jsonify({
            'id': new_person.id,
            'name': new_person.name,
            'age': new_person.age
        }), 201
        
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/persons/<int:id>', methods=['PUT', 'PATCH'])
def update_person(id):
    try:
        person = Person.query.get_or_404(id)
        data = request.get_json()
        
        if 'name' in data:
            person.name = data['name']
        if 'age' in data:
            person.age = data['age']
            
        handle_db_operations()
        return jsonify({
            'id': person.id,
            'name': person.name,
            'age': person.age
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/persons/<int:id>', methods=['DELETE'])
def delete_person(id):
    try:
        person = Person.query.get_or_404(id)
        db.session.delete(person)
        handle_db_operations()
        return jsonify({'message': 'Person deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ----------------- ADDRESS ENDPOINTS -----------------
@app.route('/api/addresses', methods=['POST'])
def create_address():
    try:
        data = request.get_json()
        validate_required_fields(data, ['street', 'city', 'person_id'])
        
        new_address = Address(
            street=data['street'],
            city=data['city'],
            person_id=data['person_id']
        )
        db.session.add(new_address)
        handle_db_operations()
        
        return jsonify({
            'id': new_address.id,
            'street': new_address.street,
            'city': new_address.city,
            'person_id': new_address.person_id
        }), 201
        
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/addresses/<int:id>', methods=['PUT', 'PATCH'])
def update_address(id):
    try:
        address = Address.query.get_or_404(id)
        data = request.get_json()
        
        if 'street' in data:
            address.street = data['street']
        if 'city' in data:
            address.city = data['city']
        if 'person_id' in data:
            address.person_id = data['person_id']
            
        handle_db_operations()
        return jsonify({
            'id': address.id,
            'street': address.street,
            'city': address.city,
            'person_id': address.person_id
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/addresses/<int:id>', methods=['DELETE'])
def delete_address(id):
    try:
        address = Address.query.get_or_404(id)
        db.session.delete(address)
        handle_db_operations()
        return jsonify({'message': 'Address deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ----------------- PHONE ENDPOINTS -----------------
@app.route('/api/phones', methods=['POST'])
def create_phone():
    try:
        data = request.get_json()
        validate_required_fields(data, ['number', 'type', 'person_id'])
        
        new_phone = Phone(
            number=data['number'],
            type=data['type'],
            person_id=data['person_id']
        )
        db.session.add(new_phone)
        handle_db_operations()
        
        return jsonify({
            'id': new_phone.id,
            'number': new_phone.number,
            'type': new_phone.type,
            'person_id': new_phone.person_id
        }), 201
        
    except ValueError as ve:
        return jsonify({'error': str(ve)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/phones/<int:id>', methods=['PUT', 'PATCH'])
def update_phone(id):
    try:
        phone = Phone.query.get_or_404(id)
        data = request.get_json()
        
        if 'number' in data:
            phone.number = data['number']
        if 'type' in data:
            phone.type = data['type']
        if 'person_id' in data:
            phone.person_id = data['person_id']
            
        handle_db_operations()
        return jsonify({
            'id': phone.id,
            'number': phone.number,
            'type': phone.type,
            'person_id': phone.person_id
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/phones/<int:id>', methods=['DELETE'])
def delete_phone(id):
    try:
        phone = Phone.query.get_or_404(id)
        db.session.delete(phone)
        handle_db_operations()
        return jsonify({'message': 'Phone deleted successfully'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    db.create_all()
    app.run(debug=True)

