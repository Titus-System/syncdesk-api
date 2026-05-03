from fastapi import status
from app.core.exceptions import AppHTTPException


class AttendanceNotFoundException(AppHTTPException):
    def __init__(self, triage_id: str) -> None:
        super().__init__(
            status_code=status.HTTP_404_NOT_FOUND,
            title="Attendance Not Found",
            detail=f"Attendance {triage_id} not found."
        )


class AttendanceCreationException(AppHTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            title="Attendance Creation Error",
            detail="Attendance was created but could not be loaded afterward. Please try again."
        )


class AttendanceNotFinishedException(AppHTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            title="Attendance Not Finished",
            detail="Attendance is not finished yet."
        )


class AttendanceAlreadyEvaluatedException(AppHTTPException):
    def __init__(self) -> None:
        super().__init__(
            status_code=status.HTTP_409_CONFLICT,
            title="Attendance Already Evaluated",
            detail="Attendance has already been evaluated."
        )


class MissingClientDataException(AppHTTPException):
    def __init__(self, detail: str = "Missing client data to create attendance.") -> None:
        super().__init__(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            title="Missing Client Data",
            detail=detail
        )