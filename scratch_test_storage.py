import sys
sys.path.append('.')
from services.model_interface import screen_sequence
from services.storage import save_screening_case, get_screening

seq = "ATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGC"
res = screen_sequence(seq, "DNA")
print("Response ok:", res.get("ok"))

if res.get("ok"):
    case_id = save_screening_case(seq, "DNA", res)
    print("Saved case:", case_id)
    retrieved = get_screening(case_id)
    print("Retrieved case ok")
