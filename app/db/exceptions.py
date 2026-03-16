class ResourceAlreadyExistsError(Exception):
    def __init__(self, resource_name: str, identifier: str | int):
        self.resource_name = resource_name
        self.identifier = identifier
        super().__init__(f"{resource_name} with identifier {identifier} already exists")


class ResourceNotFoundError(Exception):
    def __init__(self, resource_name: str, identifier: str | int):
        self.resource_name = resource_name
        self.identifier = identifier
        super().__init__(f"{resource_name} with identifier {identifier} does not exists")
