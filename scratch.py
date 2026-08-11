from cpd.data_loader import CpdData
from cpd.bot import _resolve_for_name
from cpd.formatter import certificate_report, summary_report
dl = CpdData('data')
dl.ensure_loaded()
part = _resolve_for_name(dl, 'HAO SREYSROAS')
tr = dl.trainings_for(part.participant_id, part.name, part.khmer_name)
cert = dl.certificates_for(part.participant_id, part.name, part.khmer_name)
print(summary_report(part, tr, cert))
