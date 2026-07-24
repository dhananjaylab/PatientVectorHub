"""
HL7 v2.x message parsing via python-hl7 (`import hl7`).

Chosen over hl7apy: hl7apy's last PyPI release (1.3.5) has had no update
in over a year and shows as an inactive project on independent
maintenance trackers; python-hl7 is actively maintained and explicitly
supports Python 3.9-3.13, matching this repo's Python 3.11 target. See
docs/PHASE_4_IMPLEMENTATION_PLAN.md footnote [2].

API used here (verified against python-hl7's current docs):
  - message.segment(id)   -> first matching Segment, KeyError if none
  - message.segments(id)  -> list of all matching Segments, KeyError if none
  - segment[n]             -> field n (0 = segment ID itself)
"""
import hl7

from .r2_client import get_object_bytes


class HL7Parser:
    """Flatten an HL7 v2 message's clinically relevant segments into text
    suitable for chunking + embedding. Not a full HL7 renderer — pulls
    PID demographics, OBX observations, and DG1 diagnoses only, matching
    what the RAG query pipeline actually needs to retrieve on."""

    def extract(self, r2_uri: str) -> str:
        raw_bytes = get_object_bytes(r2_uri)
        message = hl7.parse(raw_bytes.decode("utf-8", errors="replace"))
        parts: list[str] = []

        try:
            pid = message.segment("PID")
            dob = str(pid[7]) if len(pid) > 7 else ""
            sex = str(pid[8]) if len(pid) > 8 else ""
            if dob or sex:
                parts.append(f"DOB: {dob}  Sex: {sex}")
        except (KeyError, IndexError):
            pass

        try:
            for obx in message.segments("OBX"):
                try:
                    obs_id = obx[3]
                    value = obx[5]
                    unit = obx[6] if len(obx) > 6 else ""
                    parts.append(f"Obs: {obs_id} = {value} {unit}".rstrip())
                except IndexError:
                    continue
        except KeyError:
            pass  # no OBX segments in this message

        try:
            for dg1 in message.segments("DG1"):
                try:
                    parts.append(f"Dx: {dg1[3]} — {dg1[4]}")
                except IndexError:
                    continue
        except KeyError:
            pass  # no DG1 segments in this message

        return "\n".join(parts)
