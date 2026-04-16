from app.domains.products.repositories import ProductRepository


class ProductService:
    def __init__(self, repo: ProductRepository) -> None:
        self.repo = repo
