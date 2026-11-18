from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

app = FastAPI(title="Inventory demo")
stock = {"desk-lamp": 12, "notebook": 50}


class Reservation(BaseModel):
    sku: str
    quantity: int = Field(gt=0)


@app.get("/products")
def list_products() -> dict[str, int]:
    """Return the catalogue and available quantity for each product."""
    return stock.copy()


@app.post("/reservations")
def reserve_product(request: Reservation):
    """Reserve stock when the product exists and enough quantity is available."""
    if request.sku not in stock:
        raise HTTPException(404, "Product not found")
    if request.quantity > stock[request.sku]:
        raise HTTPException(409, "Insufficient stock")
    stock[request.sku] -= request.quantity
    return {"sku": request.sku, "reserved": request.quantity, "remaining": stock[request.sku]}
