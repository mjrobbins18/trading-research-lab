"""Run the frozen version-2 parser on the fresh comparison corpus."""
import hashlib,json,time
from pathlib import Path
from qualified_extractor import extract
from qualified_validator import validate


def main():
    root=Path('outputs/qualified-extraction');run=root/'run-01'
    protocol=json.loads((root/'protocol.json').read_text())
    for name,h in protocol['hashes'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=h:raise ValueError('Pre-selection artifact changed')
    started=time.perf_counter()
    docs=json.loads((root/'documents.json').read_text())
    answers=[extract(d) for d in docs]
    validations=[{'document_id':d['document_id'],**validate(a,d)} for a,d in zip(answers,docs)]
    elapsed=time.perf_counter()-started
    (run/'code-answers.json').write_text(json.dumps(answers,indent=2)+'\n')
    (run/'code-validation.json').write_text(json.dumps(validations,indent=2)+'\n')
    (run/'code-timing.json').write_text(json.dumps({'elapsed_seconds':elapsed,'external_model_calls':0},indent=2)+'\n')
    print(f'Parsed {len(answers)} documents. Validation failures: {sum(not v["passed"] for v in validations)}. No reference key read.')

if __name__=='__main__':main()
