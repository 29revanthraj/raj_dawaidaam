"""Private address book. Coordinates are supplied by the user, not inferred from text."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from . import accounts, db

router = APIRouter(prefix="/api/addresses", tags=["addresses"])


class HomeAddress(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    label: str = Field(min_length=1, max_length=60)
    recipient: str = Field(min_length=1, max_length=100)
    line1: str = Field(min_length=1, max_length=200)
    line2: str = Field(default="", max_length=200)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    pincode: str = Field(pattern=r"^[1-9][0-9]{5}$")
    lat: float | None = Field(default=None, ge=-90, le=90, allow_inf_nan=False)
    lng: float | None = Field(default=None, ge=-180, le=180, allow_inf_nan=False)

    @model_validator(mode="after")
    def coordinates_together(self):
        if (self.lat is None) != (self.lng is None):
            raise ValueError("Provide both coordinates or leave both empty")
        return self


def get_address(address_id, user_id):
    with db.conn() as c:
        row = c.execute("SELECT * FROM home_addresses WHERE id=? AND user_id=?", (address_id, user_id)).fetchone()
    if not row:
        raise HTTPException(404, "Saved address not found")
    return {key: row[key] for key in row.keys() if key != "user_id"}


@router.get("")
def list_addresses(user=Depends(accounts.current_user)):
    with db.conn() as c:
        rows = c.execute("SELECT * FROM home_addresses WHERE user_id=? ORDER BY id", (user["id"],)).fetchall()
    return [{key: row[key] for key in row.keys() if key != "user_id"} for row in rows]


@router.post("", status_code=201)
def add_address(address: HomeAddress, user=Depends(accounts.current_user)):
    with db.conn() as c:
        cursor = c.execute("""INSERT INTO home_addresses(user_id,label,recipient,line1,line2,city,state,pincode,lat,lng)
                              VALUES(:user_id,:label,:recipient,:line1,:line2,:city,:state,:pincode,:lat,:lng)""",
                           {**address.model_dump(), "user_id": user["id"]})
        address_id = cursor.lastrowid
    return get_address(address_id, user["id"])


@router.put("/{address_id}")
def edit_address(address_id: int, address: HomeAddress, user=Depends(accounts.current_user)):
    with db.conn() as c:
        cursor = c.execute("""UPDATE home_addresses SET label=:label,recipient=:recipient,line1=:line1,
                              line2=:line2,city=:city,state=:state,pincode=:pincode,lat=:lat,lng=:lng
                              WHERE id=:id AND user_id=:user_id""",
                           {**address.model_dump(), "id": address_id, "user_id": user["id"]})
        if not cursor.rowcount:
            raise HTTPException(404, "Saved address not found")
    return get_address(address_id, user["id"])


@router.delete("/{address_id}")
def delete_address(address_id: int, user=Depends(accounts.current_user)):
    with db.conn() as c:
        cursor = c.execute("DELETE FROM home_addresses WHERE id=? AND user_id=?", (address_id, user["id"]))
        if not cursor.rowcount:
            raise HTTPException(404, "Saved address not found")
    return {"ok": True}