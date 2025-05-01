from fastapi import FastAPI, Depends, HTTPException, Body
from sqlalchemy import Column, Integer, String, Float, Table, select,text, ForeignKey
from sqlalchemy.orm import Session
from database import get_db1, get_db2, db1_engine, db2_engine, metadata_db1, metadata_db2
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import json
import trino



app = FastAPI(title="Multi-Database API")

# Pydantic models for request/response
class UserBase(BaseModel):
    name: str
    email: str

class UserCreate(UserBase):
    pass

class User(UserBase):
    id: int
    
    class Config:
        orm_mode = True

class ProductBase(BaseModel):
    name: str
    price: float
    user_id: int  # Reference to user in the other database

class ProductCreate(ProductBase):
    pass

class Product(ProductBase):
    id: int
    
    class Config:
        orm_mode = True

class UserWithProducts(User):
    products: List[Product] = []

# Add these new models for query execution
class QueryRequest(BaseModel):
    query: str
    database: str = "db1"  # Options: db1, db2, trino
class QueryResponse(BaseModel):
    results: List[Dict[str, Any]]
    columns: List[str]
    row_count: int


@app.post("/execute-query", response_model=QueryResponse)
def execute_query(request: QueryRequest = Body(...)):
    """
    Execute a SQL query against the specified database.
    
    Parameters:
    - query: SQL query to execute
    - database: Which database to query (db1, db2, or trino)
    
    Returns:
    - Query results with column names and row count
    """
    try:
        if request.database.lower() == "db1":
            # Execute against first database
            with db1_engine.connect() as connection:
                result = connection.execute(text(request.query))
                columns = result.keys()
                rows = [dict(zip(columns, row)) for row in result.fetchall()]
                return {
                    "results": rows,
                    "columns": columns,
                    "row_count": len(rows)
                }
                
        elif request.database.lower() == "db2":
            # Execute against second database
            with db2_engine.connect() as connection:
                result = connection.execute(text(request.query))
                columns = result.keys()
                rows = [dict(zip(columns, row)) for row in result.fetchall()]
                return {
                    "results": rows,
                    "columns": columns,
                    "row_count": len(rows)
                }
                
        elif request.database.lower() == "trino":
            # Execute against Trino
            conn = trino.dbapi.connect(
                host="trino",
                port=8080,
                user="trino",
                catalog="postgresql",
                schema="public",
            )
            
            cursor = conn.cursor()
            cursor.execute(request.query)
            
            if cursor.description:
                columns = [col[0] for col in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
                return {
                    "results": rows,
                    "columns": columns,
                    "row_count": len(rows)
                }
            else:
                # For queries that don't return results (like INSERT)
                return {
                    "results": [],
                    "columns": [],
                    "row_count": 0
                }
        else:
            raise HTTPException(status_code=400, detail=f"Invalid database specified: {request.database}. Use 'db1', 'db2', or 'trino'")
            
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Query execution error: {str(e)}")


# Create example tables in both databases on startup
@app.on_event("startup")
async def startup():
    # Create tables in DB1
    users = Table(
        "users",
        metadata_db1,
        Column("id", Integer, primary_key=True),
        Column("name", String),
        Column("email", String),
    )
    metadata_db1.create_all(db1_engine)
    
    # Create tables in DB2
    products = Table(
        "products",
        metadata_db2,
        Column("id", Integer, primary_key=True),
        Column("name", String),
        Column("price", Float),
        Column("user_id", Integer, nullable=False),  # Reference to user in DB1
    )
    metadata_db2.create_all(db2_engine)
    
    # Insert sample data in DB1
    with db1_engine.connect() as conn:
        # Check if data already exists
        result = conn.execute(select(users).limit(1)).fetchone()
        if not result:
            conn.execute(users.insert().values(name="User 1", email="user1@example.com"))
            conn.execute(users.insert().values(name="User 2", email="user2@example.com"))
            conn.commit()
    
    # Insert sample data in DB2
    with db2_engine.connect() as conn:
        # Check if data already exists
        result = conn.execute(select(products).limit(1)).fetchone()
        if not result:
            conn.execute(products.insert().values(name="Product 1", price=100.50, user_id=1))
            conn.execute(products.insert().values(name="Product 2", price=200.75, user_id=1))
            conn.execute(products.insert().values(name="Product 3", price=150.25, user_id=2))
            conn.commit()

# API endpoints
@app.get("/")
def read_root():
    return {
        "message": "FastAPI backend connected to multiple PostgreSQL databases",
        "endpoints": {
            "users": "/users - data from first database (db)",
            "products": "/products - data from second database (db2)",
            "users_with_products": "/users/{user_id}/products - get user with their products",
            "trino": "Access Trino at http://localhost:8080"
        }
    }

@app.get("/users", response_model=List[User])
def read_users(db: Session = Depends(get_db1)):
    users = Table("users", metadata_db1, autoload_with=db1_engine)
    result = db.execute(select(users)).fetchall()
    return [{"id": row.id, "name": row.name, "email": row.email} for row in result]

@app.post("/users", response_model=User)
def create_user(user: UserCreate = Body(...), db: Session = Depends(get_db1)):
    users = Table("users", metadata_db1, autoload_with=db1_engine)
    result = db.execute(users.insert().values(name=user.name, email=user.email))
    db.commit()
    return {"id": result.inserted_primary_key[0], "name": user.name, "email": user.email}

@app.get("/products", response_model=List[Product])
def read_products(db: Session = Depends(get_db2)):
    products = Table("products", metadata_db2, autoload_with=db2_engine)
    result = db.execute(select(products)).fetchall()
    return [{"id": row.id, "name": row.name, "price": row.price, "user_id": row.user_id} for row in result]

@app.post("/products", response_model=Product)
def create_product(product: ProductCreate = Body(...), db1: Session = Depends(get_db1), db2: Session = Depends(get_db2)):
    # First, verify that the user exists in DB1
    users = Table("users", metadata_db1, autoload_with=db1_engine)
    user = db1.execute(select(users).where(users.c.id == product.user_id)).fetchone()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {product.user_id} not found")
    
    # If user exists, create the product in DB2
    products = Table("products", metadata_db2, autoload_with=db2_engine)
    result = db2.execute(products.insert().values(
        name=product.name, 
        price=product.price,
        user_id=product.user_id
    ))
    db2.commit()
    
    return {
        "id": result.inserted_primary_key[0], 
        "name": product.name, 
        "price": product.price,
        "user_id": product.user_id
    }

@app.get("/users/{user_id}/products", response_model=UserWithProducts)
def get_user_with_products(user_id: int, db1: Session = Depends(get_db1), db2: Session = Depends(get_db2)):
    # Get user from DB1
    users = Table("users", metadata_db1, autoload_with=db1_engine)
    user = db1.execute(select(users).where(users.c.id == user_id)).fetchone()
    if not user:
        raise HTTPException(status_code=404, detail=f"User with ID {user_id} not found")
    
    # Get products for this user from DB2
    products = Table("products", metadata_db2, autoload_with=db2_engine)
    products_result = db2.execute(select(products).where(products.c.user_id == user_id)).fetchall()
    
    # Combine the data
    user_data = {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "products": [
            {
                "id": product.id,
                "name": product.name,
                "price": product.price,
                "user_id": product.user_id
            } 
            for product in products_result
        ]
    }
    
    return user_data

@app.get("/query-both")
def query_both(db1: Session = Depends(get_db1), db2: Session = Depends(get_db2)):
    # Query from first database
    users = Table("users", metadata_db1, autoload_with=db1_engine)
    users_result = db1.execute(select(users)).fetchall()
    users_data = [{"id": row.id, "name": row.name, "email": row.email} for row in users_result]
    
    # Query from second database
    products = Table("products", metadata_db2, autoload_with=db2_engine)
    products_result = db2.execute(select(products)).fetchall()
    products_data = [{"id": row.id, "name": row.name, "price": row.price, "user_id": row.user_id} for row in products_result]
    
    # Combine data to show the relationship
    users_with_products = []
    for user in users_data:
        user_products = [p for p in products_data if p["user_id"] == user["id"]]
        users_with_products.append({
            **user,
            "products": user_products
        })
    
    return {
        "users": users_data,
        "products": products_data,
        "users_with_products": users_with_products
    }