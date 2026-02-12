from supabase import Client
from typing import List, Optional
from passlib.context import CryptContext

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class CRUDUser:
    def __init__(self, supabase_client: Client):
        self.client = supabase_client

    def get_multi(
        self,
        skip: int = 0,
        limit: int = 20,
        is_admin: bool = False
    ) -> List[dict]:

        if not is_admin:
            raise Exception("Not authorized")

        response = (
            self.client.table("users")
            .select("user_id,email,user_name,full_name,phone,loyalty_points,created_at,updated_at")
            .order("created_at", desc=True)
            .range(skip, skip + limit - 1)
            .execute()
        )

        return response.data

    def get_by_id(
        self,
        user_id: int,
        current_user_id: int,
        is_admin: bool = False
    ) -> Optional[dict]:

        if not is_admin and user_id != current_user_id:
            raise Exception("Not authorized")

        response = (
            self.client.table("users")
            .select("user_id,email,user_name,full_name,phone,loyalty_points,created_at,updated_at")
            .eq("user_id", user_id)
            .execute()
        )

        if not response.data:
            return None

        return response.data[0]

    def create(self, user_in: dict) -> dict:

        # Hash password properly
        hashed_password = pwd_context.hash(user_in["password"])

        insert_data = {
            "email": user_in["email"],
            "user_name": user_in["user_name"],
            "full_name": user_in["full_name"],
            "phone": user_in["phone"],
            "password_hash": hashed_password,
        }

        response = self.client.table("users").insert(insert_data).execute()

        if not response.data:
            raise Exception("User creation failed")

        return response.data[0]


    def update(
        self,
        user_id: int,
        user_in: dict,
        current_user_id: int,
        is_admin: bool = False
    ) -> Optional[dict]:

        if not is_admin and user_id != current_user_id:
            raise Exception("Not authorized")

        # Only allow safe fields
        allowed_fields = {"full_name", "phone"}

        safe_data = {
            key: value
            for key, value in user_in.items()
            if key in allowed_fields
        }

        if not safe_data:
            return None

        response = (
            self.client.table("users")
            .update(safe_data)
            .eq("user_id", user_id)
            .execute()
        )

        if not response.data:
            return None

        return response.data[0]


    def delete(
        self,
        user_id: int,
        current_user_id: int,
        is_admin: bool = False
    ) -> bool:

        if not is_admin and user_id != current_user_id:
            raise Exception("Not authorized")

        response = (
            self.client.table("users")
            .update({"is_active": False})
            .eq("user_id", user_id)
            .execute()
        )

        return bool(response.data)


    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)


    def get_by_email(self, email: str) -> Optional[dict]:
        response = (
            self.client.table("users")
            .select("*")
            .eq("email", email)
            .execute()
        )

        if not response.data:
            return None

        return response.data[0]
