from enum import Enum

class TriageState(str, Enum):
    MAIN_MENU = "A"                 
    CHOOSING_PRODUCT_PROBLEM = "B"    
    CHOOSING_QUESTION_TYPE = "C"         
    REQUESTING_ACCESS = "D"          
    WAITING_FAILURE_TEXT = "F"         
    WAITING_FEATURE_TEXT = "G"        
    SHOWING_DEADLINES = "X"                
    SHOWING_MANUAL = "J"                
    SHOWING_EMAIL = "L"                 
    ANYTHING_ELSE = "H"             
    TICKET_CREATED = "E"                 
    SERVICE_FINISHED = "I"


class AttendanceStatus(Enum):
    OPENED = "opened"
    IN_PROGRESS = "in_progress"
    FINISHED = "finished"