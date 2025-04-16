from datetime import datetime
from typing import Any, Dict, List, Optional, Type, Union
from fastapi import Depends, FastAPI, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, validator
from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Boolean, Float, or_, inspect, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import Session, relationship, sessionmaker

# Database setup
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

# --------------- SQLAlchemy Models ---------------
class PersonDB(Base):
    __tablename__ = "persons"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    age = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    addresses = relationship("AddressDB", back_populates="person")
    phones = relationship("PhoneDB", back_populates="person")

class AddressDB(Base):
    __tablename__ = "addresses"
    id = Column(Integer, primary_key=True, index=True)
    street = Column(String(100))
    city = Column(String(50))
    person_id = Column(Integer, ForeignKey("persons.id"))
    person = relationship("PersonDB", back_populates="addresses")

class PhoneDB(Base):
    __tablename__ = "phones"
    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(20))
    type = Column(String(10))  # 'home', 'work', etc.
    person_id = Column(Integer, ForeignKey("persons.id"))
    person = relationship("PersonDB", back_populates="phones")

Base.metadata.create_all(bind=engine)

# --------------- Pydantic Models ---------------
class PhoneBase(BaseModel):
    number: str = Field(..., max_length=20)
    type: str = Field(..., max_length=10)
    person_id: int

    @validator('type')
    def validate_phone_type(cls, v):
        if v.lower() not in ['home', 'work', 'mobile']:
            raise ValueError('Phone type must be home, work, or mobile')
        return v.title()

class PhoneCreate(PhoneBase):
    pass

class PhoneResponse(PhoneBase):
    id: int
    class Config:
        orm_mode = True

class AddressBase(BaseModel):
    street: str = Field(..., max_length=100)
    city: str = Field(..., max_length=50)
    person_id: int

class AddressCreate(AddressBase):
    pass

class AddressResponse(AddressBase):
    id: int
    class Config:
        orm_mode = True

class PersonBase(BaseModel):
    name: str = Field(..., max_length=100)
    age: int = Field(..., gt=0)

class PersonCreate(PersonBase):
    pass

class PersonResponse(PersonBase):
    id: int
    created_at: datetime
    addresses: List[AddressResponse] = []
    phones: List[PhoneResponse] = []
    class Config:
        orm_mode = True

# --------------- FastAPI Setup ---------------
app = FastAPI()

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --------------- Helper Functions ---------------
def parse_value(value: str, col_type: Type[Column]) -> Union[str, int, float, bool, datetime]:
    """Convert query string values to appropriate Python types"""
    try:
        if isinstance(col_type, DateTime):
            return datetime.fromisoformat(value)
        elif isinstance(col_type, Integer):
            return int(value)
        elif isinstance(col_type, Float):
            return float(value)
        elif isinstance(col_type, Boolean):
            return value.lower() in ['true', '1', 'yes']
        return value
    except (ValueError, TypeError):
        return value  # Return as string if conversion fails

def build_filters(model: Type[Base], filters: Dict[str, Any]) -> List[Any]:
    """Build SQLAlchemy filters from query parameters"""
    query_filters = []
    inspector = inspect(model)
    
    for key, value in filters.items():
        if '__' in key:
            rel_name, rel_field = key.split('__', 1)
            relationship = getattr(model, rel_name, None)
            if relationship and hasattr(relationship.property.mapper.class_, rel_field):
                rel_model = relationship.property.mapper.class_
                rel_col = getattr(rel_model, rel_field)
                parsed_value = parse_value(value, rel_col.type)
                if isinstance(rel_col.type, String):
                    query_filters.append(rel_col.ilike(f'%{parsed_value}%'))
                else:
                    query_filters.append(rel_col == parsed_value)
        else:
            column = inspector.columns.get(key)
            if column:
                col_type = column.type
                parsed_value = parse_value(value, col_type)
                if isinstance(col_type, String):
                    query_filters.append(getattr(model, key).ilike(f'%{parsed_value}%'))
                else:
                    query_filters.append(getattr(model, key) == parsed_value)
    return query_filters

def build_query(
    model: Type[Base],
    db: Session,
    filters: Dict[str, Any],
    page: int = 1,
    per_page: int = 10,
    sort: Optional[str] = None,
    search: Optional[str] = None
) -> Dict[str, Any]:
    """Build filtered and paginated query"""
    query = db.query(model)
    
    # Apply search across all string fields
    if search:
        search_filters = []
        for column in inspect(model).columns:
            if isinstance(column.type, String):
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
    total = query.count()
    paginated = query.offset((page - 1) * per_page).limit(per_page).all()
    
    return {
        "data": paginated,
        "total": total,
        "page": page,
        "per_page": per_page
    }

# --------------- API Endpoints ---------------
@app.get("/api/persons", response_model=Dict[str, Any])
def get_persons(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    sort: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    filters: Dict[str, Any] = Depends(lambda request: dict(request.query_params))
):
    special_params = ['page', 'per_page', 'sort', 'search']
    clean_filters = {k: v for k, v in filters.items() if k not in special_params}
    
    result = build_query(
        model=PersonDB,
        db=db,
        filters=clean_filters,
        page=page,
        per_page=per_page,
        sort=sort,
        search=search
    )
    return result

@app.post("/api/persons", response_model=PersonResponse, status_code=status.HTTP_201_CREATED)
def create_person(person: PersonCreate, db: Session = Depends(get_db)):
    db_person = PersonDB(**person.dict())
    db.add(db_person)
    db.commit()
    db.refresh(db_person)
    return db_person

@app.put("/api/persons/{person_id}", response_model=PersonResponse)
def update_person(person_id: int, person: PersonCreate, db: Session = Depends(get_db)):
    db_person = db.query(PersonDB).filter(PersonDB.id == person_id).first()
    if not db_person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    for key, value in person.dict().items():
        setattr(db_person, key, value)
    
    db.commit()
    db.refresh(db_person)
    return db_person

@app.delete("/api/persons/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_person(person_id: int, db: Session = Depends(get_db)):
    db_person = db.query(PersonDB).filter(PersonDB.id == person_id).first()
    if not db_person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    db.delete(db_person)
    db.commit()

# --------------- Address Endpoints ---------------
@app.get("/api/addresses", response_model=Dict[str, Any])
def get_addresses(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    sort: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    filters: Dict[str, Any] = Depends(lambda request: dict(request.query_params))
):
    special_params = ['page', 'per_page', 'sort', 'search']
    clean_filters = {k: v for k, v in filters.items() if k not in special_params}
    
    result = build_query(
        model=AddressDB,
        db=db,
        filters=clean_filters,
        page=page,
        per_page=per_page,
        sort=sort,
        search=search
    )
    return result

@app.post("/api/addresses", response_model=AddressResponse, status_code=status.HTTP_201_CREATED)
def create_address(address: AddressCreate, db: Session = Depends(get_db)):
    db_address = AddressDB(**address.dict())
    db.add(db_address)
    db.commit()
    db.refresh(db_address)
    return db_address

@app.put("/api/addresses/{address_id}", response_model=AddressResponse)
def update_address(address_id: int, address: AddressCreate, db: Session = Depends(get_db)):
    db_address = db.query(AddressDB).filter(AddressDB.id == address_id).first()
    if not db_address:
        raise HTTPException(status_code=404, detail="Address not found")
    
    for key, value in address.dict().items():
        setattr(db_address, key, value)
    
    db.commit()
    db.refresh(db_address)
    return db_address

@app.delete("/api/addresses/{address_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_address(address_id: int, db: Session = Depends(get_db)):
    db_address = db.query(AddressDB).filter(AddressDB.id == address_id).first()
    if not db_address:
        raise HTTPException(status_code=404, detail="Address not found")
    
    db.delete(db_address)
    db.commit()

# --------------- Phone Endpoints ---------------
@app.get("/api/phones", response_model=Dict[str, Any])
def get_phones(
    db: Session = Depends(get_db),
    page: int = Query(1, ge=1),
    per_page: int = Query(10, ge=1, le=100),
    sort: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    filters: Dict[str, Any] = Depends(lambda request: dict(request.query_params))
):
    special_params = ['page', 'per_page', 'sort', 'search']
    clean_filters = {k: v for k, v in filters.items() if k not in special_params}
    
    result = build_query(
        model=PhoneDB,
        db=db,
        filters=clean_filters,
        page=page,
        per_page=per_page,
        sort=sort,
        search=search
    )
    return result

@app.post("/api/phones", response_model=PhoneResponse, status_code=status.HTTP_201_CREATED)
def create_phone(phone: PhoneCreate, db: Session = Depends(get_db)):
    db_phone = PhoneDB(**phone.dict())
    db.add(db_phone)
    db.commit()
    db.refresh(db_phone)
    return db_phone

@app.put("/api/phones/{phone_id}", response_model=PhoneResponse)
def update_phone(phone_id: int, phone: PhoneCreate, db: Session = Depends(get_db)):
    db_phone = db.query(PhoneDB).filter(PhoneDB.id == phone_id).first()
    if not db_phone:
        raise HTTPException(status_code=404, detail="Phone not found")
    
    for key, value in phone.dict().items():
        setattr(db_phone, key, value)
    
    db.commit()
    db.refresh(db_phone)
    return db_phone

@app.delete("/api/phones/{phone_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_phone(phone_id: int, db: Session = Depends(get_db)):
    db_phone = db.query(PhoneDB).filter(PhoneDB.id == phone_id).first()
    if not db_phone:
        raise HTTPException(status_code=404, detail="Phone not found")
    
    db.delete(db_phone)
    db.commit()

########### To Run ##############################
# pip install fastapi sqlalchemy uvicorn python-multipart pydantic[email]
# uvicorn fastapi_app:app --reload
# http://localhost:8000/docs
# http://localhost:8000/redoc
