from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PostalAddress:
    # address
    name: str | None
    street: str | None
    locality: str | None
    postalCode: str | None = None
    region: str | None = None
    country: str | None = None

    def __str__(self):
        return f"""
        {self.name}
        {self.street}
        {self.locality}, {self.postalCode} 
        {self.region} 
        {self.country}
        """
