# Logic & Legacy: Data Validation Architecture
# Demonstrates why manual validation fails at scale, the limitations of 
# native Python alternatives (Dataclasses/NamedTuples) at the network boundary,
# and why Pydantic is the enterprise standard for data parsing.

import json
from dataclasses import dataclass
from typing import NamedTuple, Optional
from pydantic import BaseModel, ValidationError, field_validator, EmailStr

# ==========================================
# 1. THE NIGHTMARE: MANUAL VALIDATION
# ==========================================

def manual_user_validation(payload: dict) -> dict:
    """
    The old way. You must manually check for key existence, 
    verify types, and handle coercion (string "25" to int 25).
    """
    print("\n--- 1. MANUAL VALIDATION ---")
    
    if "username" not in payload:
        raise ValueError("Missing 'username'")
    if not isinstance(payload["username"], str):
        raise ValueError("'username' must be a string")
        
    if "age" not in payload:
        raise ValueError("Missing 'age'")
    
    # Manual Coercion: Network payloads are often strings
    try:
        age = int(payload["age"])
    except (ValueError, TypeError):
        raise ValueError("'age' must be an integer or a numeric string")
        
    if age < 18:
        raise ValueError("User must be at least 18 years old")
        
    return {"username": payload["username"], "age": age}

try:
    # We pass age as a string, proving the manual code has to coerce it.
    valid_data = manual_user_validation({"username": "admin", "age": "25"})
    print(f"✅ Manual Passed: {valid_data}")
except ValueError as e:
    print(f"❌ Error: {e}")

"""
EXPECTED OUTPUT:
--- 1. MANUAL VALIDATION ---
✅ Manual Passed: {'username': 'admin', 'age': 25}
"""


# ==========================================
# 2. THE NATIVE ALTERNATIVES (NamedTuples & Dataclasses)
# ==========================================

print("\n--- 2. NATIVE ALTERNATIVES AT THE BOUNDARY ---")

# A. NamedTuple (Great for immutability, terrible for network validation)
class UserTuple(NamedTuple):
    username: str
    age: int

# Python does NOT enforce the type hints at runtime.
tuple_user = UserTuple(username="guest", age="twenty")
print(f"NamedTuple Output: {tuple_user.age} (Type: {type(tuple_user.age)}) - Notice it didn't crash on 'twenty'!")


# B. Dataclass (Great for internal OOP, terrible for network boundaries)
@dataclass
class UserDataclass:
    username: str
    age: int

# Dataclasses also do NOT coerce or validate types out of the box.
dc_user = UserDataclass(username="guest", age="25")
print(f"Dataclass Output: {dc_user.age} (Type: {type(dc_user.age)}) - It kept '25' as a string!")

"""
EXPECTED OUTPUT:
--- 2. NATIVE ALTERNATIVES AT THE BOUNDARY ---
NamedTuple Output: twenty (Type: <class 'str'>) - Notice it didn't crash on 'twenty'!
Dataclass Output: 25 (Type: <class 'str'>) - It kept '25' as a string!
"""


# ==========================================
# 3. THE ENTERPRISE STANDARD: PYDANTIC
# ==========================================

print("\n--- 3. PYDANTIC BORDER CONTROL ---")

class UserSchema(BaseModel):
    username: str
    age: int
    email: EmailStr  # Pydantic natively validates email regex formats
    bio: Optional[str] = None  # Safely handles missing optional fields

    # Complex Business Logic Validation
    @field_validator('age')
    @classmethod
    def check_age(cls, v: int) -> int:
        if v < 18:
            raise ValueError('User must be at least 18 years old')
        return v

# Scenario A: Valid Data (With Coercion)
try:
    # Notice 'age' is a string. Pydantic will smartly cast it to an int.
    raw_payload = {"username": "ceo_user", "age": "42", "email": "ceo@logicandlegacy.com"}
    secure_user = UserSchema(**raw_payload)
    print(f"✅ Pydantic Passed: {secure_user.model_dump()}")
    print(f"   -> Age Coerced to: {type(secure_user.age)}")
except ValidationError as e:
    print(f"❌ Pydantic Error: {e}")

# Scenario B: Invalid Data (Catches multiple errors at once)
print("\n[Testing Invalid Payload]")
try:
    bad_payload = {"username": 123, "age": "sixteen", "email": "not_an_email"}
    bad_user = UserSchema(**bad_payload)
except ValidationError as e:
    # Pydantic collects ALL errors instead of failing on just the first one
    print(f"❌ Pydantic Caught Multiple Errors:\n{e.json(indent=2)}")

"""
EXPECTED OUTPUT:
--- 3. PYDANTIC BORDER CONTROL ---
✅ Pydantic Passed: {'username': 'ceo_user', 'age': 42, 'email': 'ceo@logicandlegacy.com', 'bio': None}
   -> Age Coerced to: <class 'int'>

[Testing Invalid Payload]
❌ Pydantic Caught Multiple Errors:
[
  {
    "type": "string_type",
    "loc": [
      "username"
    ],
    "msg": "Input should be a valid string",
    "input": 123
  },
  {
    "type": "int_parsing",
    "loc": [
      "age"
    ],
    "msg": "Input should be a valid integer, unable to parse string as an integer",
    "input": "sixteen"
  },
  {
    "type": "value_error",
    "loc": [
      "email"
    ],
    "msg": "value is not a valid email address: The email address is not valid. It must have exactly one @-sign.",
    "input": "not_an_email"
  }
]
"""

if __name__ == "__main__":
    pass
