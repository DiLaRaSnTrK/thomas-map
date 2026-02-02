from sqlalchemy import Column, Integer, String, Float, Boolean
from database import Base

class Place(Base):
    __tablename__ = "places"

    id = Column(Integer, primary_key=True, index=True)
    name_historic = Column(String, nullable=False)
    name_modern = Column(String, nullable=False)
    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    is_in_ottoman = Column(Boolean, default=False)
    description_tr = Column(String, default="")
    description_en = Column(String, default="")
