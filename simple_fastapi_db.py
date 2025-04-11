from fastapi import FastAPI, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from datetime import datetime
from typing import Optional, List, Dict, Any

# FastAPI setup
app = FastAPI()

# Database configuration
SQLALCHEMY_DATABASE_URL = "sqlite:///./test.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# ----------------- MODELS -----------------
class Person(Base):
    __tablename__ = "persons"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100))
    age = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)
    addresses = relationship("Address", back_populates="person")
    phones = relationship("Phone", back_populates="person")

class Address(Base):
    __tablename__ = "addresses"
    id = Column(Integer, primary_key=True, index=True)
    street = Column(String(100))
    city = Column(String(50))
    person_id = Column(Integer, ForeignKey("persons.id"))
    person = relationship("Person", back_populates="addresses")

class Phone(Base):
    __tablename__ = "phones"
    id = Column(Integer, primary_key=True, index=True)
    number = Column(String(20))
    type = Column(String(10))
    person_id = Column(Integer, ForeignKey("persons.id"))
    person = relationship("Person", back_populates="phones")

Base.metadata.create_all(bind=engine)

# ----------------- SCHEMAS -----------------
class PhoneBase(BaseModel):
    number: str
    type: str
    person_id: int

class AddressBase(BaseModel):
    street: str
    city: str
    person_id: int

class PersonBase(BaseModel):
    name: str
    age: int

class PersonCreate(PersonBase):
    pass

class PersonResponse(PersonBase):
    id: int
    created_at: datetime
    addresses: List[AddressBase] = []
    phones: List[PhoneBase] = []

    class Config:
        orm_mode = True

# ----------------- UTILITIES -----------------
def apply_filters(query, model, filters: Dict[str, Any]):
    for key, value in filters.items():
        if '__' in key:
            # Handle related models (e.g., addresses__city)
            rel_name, field_name = key.split('__', 1)
            relationship = getattr(model, rel_name)
            related_model = relationship.property.mapper.class_
            query = query.join(related_model)
            query = query.filter(getattr(related_model, field_name).ilike(f"%{value}%"))
        else:
            # Handle direct fields
            column = getattr(model, key)
            if isinstance(column.property.columns[0].type, String):
                query = query.filter(column.ilike(f"%{value}%"))
            else:
                query = query.filter(column == value)
    return query

# ----------------- PERSON ENDPOINTS -----------------
@app.get("/persons", response_model=List[PersonResponse])
def get_persons(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=1000),
    sort: Optional[str] = None,
    search: Optional[str] = None,
    **filters: str
):
    query = db.query(Person)

    # Apply search
    if search:
        query = query.filter(or_(
            Person.name.ilike(f"%{search}%"),
            Person.age.ilike(f"%{search}%")
        ))

    # Apply filters
    query = apply_filters(query, Person, filters)

    # Apply sorting
    if sort:
        sort_fields = []
        for field in sort.split(','):
            if field.startswith('-'):
                sort_fields.append(getattr(Person, field[1:]).desc())
            else:
                sort_fields.append(getattr(Person, field))
        query = query.order_by(*sort_fields)

    # Pagination
    return query.offset(skip).limit(limit).all()

@app.post("/persons", response_model=PersonResponse, status_code=status.HTTP_201_CREATED)
def create_person(person: PersonCreate, db: Session = Depends(get_db)):
    db_person = Person(**person.dict())
    db.add(db_person)
    db.commit()
    db.refresh(db_person)
    return db_person

@app.put("/persons/{person_id}", response_model=PersonResponse)
def update_person(person_id: int, person: PersonCreate, db: Session = Depends(get_db)):
    db_person = db.query(Person).filter(Person.id == person_id).first()
    if not db_person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    for key, value in person.dict().items():
        setattr(db_person, key, value)
    
    db.commit()
    db.refresh(db_person)
    return db_person

@app.delete("/persons/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_person(person_id: int, db: Session = Depends(get_db)):
    db_person = db.query(Person).filter(Person.id == person_id).first()
    if not db_person:
        raise HTTPException(status_code=404, detail="Person not found")
    
    db.delete(db_person)
    db.commit()

# ----------------- ADDRESS ENDPOINTS -----------------
@app.get("/addresses", response_model=List[AddressBase])
def get_addresses(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=1000),
    **filters: str
):
    query = apply_filters(db.query(Address), Address, filters)
    return query.offset(skip).limit(limit).all()

@app.post("/addresses", response_model=AddressBase, status_code=status.HTTP_201_CREATED)
def create_address(address: AddressBase, db: Session = Depends(get_db)):
    db_address = Address(**address.dict())
    db.add(db_address)
    db.commit()
    db.refresh(db_address)
    return db_address

# ----------------- PHONE ENDPOINTS -----------------
@app.get("/phones", response_model=List[PhoneBase])
def get_phones(
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(100, le=1000),
    **filters: str
):
    query = apply_filters(db.query(Phone), Phone, filters)
    return query.offset(skip).limit(limit).all()

@app.post("/phones", response_model=PhoneBase, status_code=status.HTTP_201_CREATED)
def create_phone(phone: PhoneBase, db: Session = Depends(get_db)):
    db_phone = Phone(**phone.dict())
    db.add(db_phone)
    db.commit()
    db.refresh(db_phone)
    return db_phone
