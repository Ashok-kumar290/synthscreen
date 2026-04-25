import sys
sys.path.append('.')
from services.model_interface import screen_sequence

print(screen_sequence("ATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGCATGC", "DNA"))
