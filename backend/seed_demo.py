"""Demo seed for Plan2Progress.

Seeds *inputs* and then runs the real pipeline over them. Nothing in this file
writes a confidence score, a completion percentage, a variance or a risk level
directly: the baseline goes in through the production schedule parser, field
reports go in through the document upload path and are parsed by the production
processor, and matching, roll-up and delay prediction are then invoked exactly
as the API invokes them. Every derived number the dashboard shows is therefore
computed by the same code that serves real traffic.

Scope of the wipe is deliberately narrow — project-scoped rows only. User
accounts, refresh tokens and the audit trail are left untouched.

Usage:  .venv/bin/python seed_demo.py
"""

from __future__ import annotations

import io
import random
import sys
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, select

from app.core.constants import (
    Discipline,
    DocumentType,
    MatchStatus,
    ProjectStatus,
    UserRole,
)
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.document import ProcessingJob, ProgressReport, UploadedFile
from app.models.matching import ActivityMatch, ExtractedActivity
from app.models.prediction import DelayModelVersion, DelayPrediction
from app.models.progress import ActualProgress
from app.models.project import Project, ProjectMembership
from app.models.reporting import GeneratedReport
from app.models.schedule import Activity, ActivityDependency, Schedule
from app.models.user import User
from app.schemas.matching import MatchRunRequest, MatchReviewDecision
from app.schemas.prediction import PredictRequest, TrainRequest
from app.schemas.schedule import ScheduleColumnMapping
from app.services.auth import RequestContext
from app.services.document import DocumentService
from app.services.matching import MatchingService
from app.services.prediction import PredictionService
from app.services.progress import ProgressService
from app.services.schedule import ScheduleService
from app.services.schedule_parser import ScheduleParser
from app.schemas.schedule import ScheduleCreate
from app.tasks.document_tasks import process_uploaded_file

RNG = random.Random(20260914)
CTX = RequestContext(ip_address="127.0.0.1", user_agent="seed_demo.py")


def log(msg: str) -> None:
    print(f"  {msg}", flush=True)


# --------------------------------------------------------------------- wipe
def wipe_project_data(db) -> None:
    """Delete project-scoped rows, newest-dependency first.

    Project only ORM-cascades to its memberships, so everything else is removed
    explicitly rather than relying on a cascade that does not exist.
    """
    for model in (
        ActivityMatch,
        ExtractedActivity,
        ActualProgress,
        DelayPrediction,
        DelayModelVersion,
        GeneratedReport,
        ProcessingJob,
        ProgressReport,
        UploadedFile,
        ActivityDependency,
        Activity,
        Schedule,
        ProjectMembership,
        Project,
    ):
        n = db.execute(delete(model)).rowcount
        if n:
            log(f"deleted {n:>5} {model.__name__}")
    db.commit()


# -------------------------------------------------------------------- users
def ensure_user(db, email: str, name: str, role: UserRole, phone: str | None) -> User:
    user = db.execute(select(User).where(User.email == email)).scalar_one_or_none()
    if user is None:
        user = User(
            email=email,
            full_name=name,
            hashed_password=hash_password("DemoPass123"),
            role=role,
            phone=phone,
            is_active=True,
        )
        db.add(user)
        db.flush()
        log(f"created user {email} ({role})")
    else:
        user.full_name, user.role, user.phone, user.is_active = name, role, phone, True
        log(f"kept user   {email} ({role})")
    return user


# ----------------------------------------------------------------- baseline
@dataclass
class Leaf:
    """One leaf activity plus the site behaviour the reports will describe."""

    code: str
    name: str
    wbs: str
    level: int
    discipline: str
    start: date
    finish: date
    qty: float
    uom: str
    slip_days: int          # >0 finished late, <=0 on or ahead of plan
    reported: bool          # whether the field ever reports on it
    children: list = field(default_factory=list)


SPREADS = [
    ("A", "Duliajan–Naharkatia", 0),
    ("B", "Naharkatia–Jorhat", 55),
    ("C", "Jorhat–Golaghat", 110),
    ("D", "Golaghat–Numaligarh", 165),
]

# (label, discipline, uom, qty per segment, duration days, share of spread offset)
STEPS = [
    ("Survey & Setting Out", Discipline.SURVEY, "m", 2800, 10, 0),
    ("Trenching", Discipline.CIVIL, "m", 2800, 22, 8),
    ("Pipe Laying", Discipline.PIPING, "m", 2800, 26, 26),
    ("Welding & NDT", Discipline.WELDING_NDT, "joints", 230, 24, 46),
    ("Coating & Wrapping", Discipline.COATING, "m", 2800, 18, 66),
    ("Backfilling & Reinstatement", Discipline.CIVIL, "m", 2800, 16, 82),
]


def build_pipeline_baseline() -> tuple[list[dict], list[Leaf]]:
    """An L1–L6 pipeline baseline with realistic durations and quantities."""
    rows: list[dict] = []
    leaves: list[Leaf] = []
    origin = date(2026, 1, 5)
    seq = 1000

    def add(code, name, wbs, level, disc, s, f, qty, uom):
        rows.append(
            {
                "Activity ID": code,
                "Activity Name": name,
                "WBS": wbs,
                "Level": level,
                "Discipline": disc,
                "Start": s.isoformat() if s else "",
                "Finish": f.isoformat() if f else "",
                "Budgeted Qty": qty if qty else "",
                "UOM": uom,
            }
        )

    add("PL0100", "Pipeline PL-02 Expansion", "1", 1, "", origin, date(2026, 12, 18), "", "")
    add("PL0200", "Pre-Construction", "1.1", 2, Discipline.SURVEY, origin, date(2026, 2, 20), "", "")

    for code, nm, disc, dur, qty, uom in [
        ("PL0210", "Site Mobilisation", Discipline.OTHER, 18, "", ""),
        ("PL0220", "Right of Way Acquisition", Discipline.SURVEY, 30, 220000, "m"),
        ("PL0230", "Topographic Survey", Discipline.SURVEY, 24, 220000, "m"),
    ]:
        s = origin
        f = s + timedelta(days=dur)
        add(code, nm, f"1.1.{code[-2:]}", 3, disc, s, f, qty, uom)
        leaves.append(
            Leaf(code, nm, f"1.1.{code[-2:]}", 3, disc, s, f, float(qty or 0), uom,
                 slip_days=RNG.choice([-2, 0, 3]), reported=True)
        )

    add("PL0300", "Pipeline Construction", "1.2", 2, Discipline.PIPING,
        date(2026, 2, 2), date(2026, 11, 20), "", "")

    for si, (letter, stretch, offset) in enumerate(SPREADS, start=1):
        sp_code = f"PL03{si}0"
        sp_start = date(2026, 2, 2) + timedelta(days=offset)
        add(sp_code, f"Spread {letter} — {stretch}", f"1.2.{si}", 3,
            Discipline.PIPING, sp_start, sp_start + timedelta(days=150), "", "")

        for ti, (label, disc, uom, qty, dur, lag) in enumerate(STEPS, start=1):
            grp = f"PL03{si}{ti}"
            g_start = sp_start + timedelta(days=lag)
            add(grp, f"{label} — Spread {letter}", f"1.2.{si}.{ti}", 4,
                disc, g_start, g_start + timedelta(days=dur + 30), "", "")

            for seg in range(1, 4):  # three segments per step
                seq += 10
                code = f"PL{seq}"
                s = g_start + timedelta(days=(seg - 1) * 9)
                f = s + timedelta(days=dur)
                name = f"{label} Segment {letter}{seg}"
                wbs = f"1.2.{si}.{ti}.{seg}"
                # Reality: most of spread A and B has run, C is part-way,
                # D has barely started. Slippage grows down the line.
                if si == 1:
                    slip, reported = RNG.choice([0, 0, -1, 2, 4]), True
                elif si == 2:
                    slip, reported = RNG.choice([0, 3, 5, 8, -2]), True
                elif si == 3:
                    slip, reported = RNG.choice([6, 9, 12, 0]), ti <= 4
                else:
                    slip, reported = RNG.choice([10, 14, 0]), ti <= 2
                add(code, name, wbs, 5, disc, s, f, qty, uom)
                leaves.append(
                    Leaf(code, name, wbs, 5, disc, s, f, float(qty), uom,
                         slip_days=slip, reported=reported)
                )

    add("PL0400", "Testing & Commissioning", "1.3", 2,
        Discipline.TESTING_PRECOMMISSIONING, date(2026, 9, 1), date(2026, 12, 18), "", "")
    for code, nm, dur, qty, uom in [
        ("PL0410", "Hydrostatic Testing", 30, 220000, "m"),
        ("PL0420", "Pre-Commissioning Checks", 24, "", ""),
        ("PL0430", "Final Handover Documentation", 20, "", ""),
    ]:
        s = date(2026, 9, 1)
        f = s + timedelta(days=dur)
        add(code, nm, f"1.3.{code[-2:]}", 3, Discipline.TESTING_PRECOMMISSIONING, s, f, qty, uom)
        leaves.append(
            Leaf(code, nm, f"1.3.{code[-2:]}", 3, Discipline.TESTING_PRECOMMISSIONING,
                 s, f, float(qty or 0), uom, slip_days=0, reported=False)
        )

    return rows, leaves


def rows_to_csv(rows: list[dict]) -> bytes:
    import csv

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=list(rows[0].keys()))
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue().encode()


MAPPING = ScheduleColumnMapping(
    activity_code="Activity ID",
    name="Activity Name",
    wbs_path="WBS",
    level="Level",
    discipline="Discipline",
    planned_start="Start",
    planned_finish="Finish",
    budgeted_quantity="Budgeted Qty",
    uom="UOM",
)


# ------------------------------------------------------------ field reports
def progress_lines(leaf: Leaf) -> list[tuple[date, str]]:
    """Report lines for one activity, written the way a site would write them.

    Each line carries a date, a percentage and usually a quantity, because the
    extractor reads those from free text and the roll-up refuses to book an
    undated line.
    """
    out: list[tuple[date, str]] = []
    planned_days = max((leaf.finish - leaf.start).days, 1)
    actual_finish = leaf.finish + timedelta(days=leaf.slip_days)
    checkpoints = [0.25, 0.5, 0.75, 1.0]
    for frac in checkpoints:
        when = leaf.start + timedelta(days=int(planned_days * frac) + max(leaf.slip_days, 0))
        pct = int(frac * 100)
        qty = round(leaf.qty * frac)
        if frac == 1.0:
            when = actual_finish
        qty_txt = f" — {qty:,} {leaf.uom} cumulative".replace(",", "") if leaf.qty else ""
        verb = "completed" if frac == 1.0 else "progressed to"
        out.append(
            (when, f"{when.isoformat()} {leaf.code} {leaf.name} {verb} {pct}%{qty_txt}")
        )
    return out


def build_dpr_documents(leaves: list[Leaf], cutoff: date) -> list[tuple[str, str, bytes]]:
    """Group the progress lines into dated daily reports."""
    by_day: dict[date, list[str]] = {}
    for leaf in leaves:
        if not leaf.reported:
            continue
        for when, line in progress_lines(leaf):
            if when <= cutoff:
                by_day.setdefault(when, []).append(line)

    docs: list[tuple[str, str, bytes]] = []
    for day in sorted(by_day):
        lines = by_day[day]
        body = [f"DAILY PROGRESS REPORT — {day.isoformat()}", ""]
        body += lines
        docs.append(
            (f"DPR_{day.isoformat()}.txt", "DAILY_PROGRESS_REPORT",
             "\n".join(body).encode())
        )
    return docs


def build_whatsapp_documents(leaves: list[Leaf], cutoff: date) -> list[tuple[str, str, bytes]]:
    """Terse field messages — the messy end of the input range.

    Deliberately written the way a supervisor actually types: no activity code,
    abbreviated discipline, shortened segment label. These are what the matcher
    has to work for, and what lands in the review band rather than being linked
    automatically.
    """
    picks = [l for l in leaves if l.reported and l.level == 5]
    short = {
        "Survey & Setting Out": "survey",
        "Trenching": "trenching",
        "Pipe Laying": "pipe laying",
        "Welding & NDT": "welding",
        "Coating & Wrapping": "coating",
        "Backfilling & Reinstatement": "backfill",
    }
    docs = []
    for i, leaf in enumerate(RNG.sample(picks, min(22, len(picks)))):
        when = min(leaf.finish, cutoff)
        label = next((v for k, v in short.items() if leaf.name.startswith(k)), "work")
        seg = leaf.name.split()[-1]
        pct = RNG.choice([45, 55, 60, 70, 80, 85])
        text = (
            f"{when.isoformat()} site update: {label} {seg.lower()} abt {pct}% done today, "
            f"crew moving on tmrw"
        )
        docs.append((f"whatsapp_message.txt", "DAILY_PROGRESS_REPORT", text.encode()))
    return docs


def build_voice_document(leaves: list[Leaf], cutoff: date) -> tuple[str, str, bytes]:
    picked = [l for l in leaves if l.reported and l.level == 5][:12]
    lines = ["CALL TRANSCRIPT — SITE SUPERVISOR CHECK-IN", ""]
    for leaf in picked[:4]:
        when = min(leaf.finish, cutoff)
        lines.append(
            f"Supervisor: {when.isoformat()} {leaf.code} {leaf.name} is at "
            f"{RNG.choice([45, 55, 65])}% as of today."
        )
    return ("vapi_call_transcript.txt", "SITE_DIARY", "\n".join(lines).encode())


def ingest(db, project_id, actor, docs) -> int:
    """Upload each document and run the real processor inline.

    The API hands this to Celery; running the task function directly keeps the
    exact same code path without requiring a broker for a seed run.
    """
    svc = DocumentService(db)
    done = 0
    for filename, doc_type, content in docs:
        _, job = svc.upload(
            project_id, actor, CTX,
            filename=filename,
            content_type="text/plain",
            content=content,
            document_type=DocumentType(doc_type),
        )
        process_uploaded_file(str(job.id))
        done += 1
    return done


# ------------------------------------------------------------------- driver
def make_project(db, *, code, name, description, client, location, status,
                 start, finish, owner, members) -> Project:
    project = Project(
        code=code, name=name, description=description,
        client_name=client, location=location, status=status,
        planned_start=start, planned_finish=finish,
        created_by_id=owner.id,
    )
    db.add(project)
    db.flush()
    for user, role in members:
        db.add(ProjectMembership(project_id=project.id, user_id=user.id, role=role))
    db.flush()
    return project


def main() -> int:
    db = SessionLocal()
    today = date.today()
    try:
        print("\n=== 1. wiping project-scoped data ===")
        wipe_project_data(db)

        print("\n=== 2. users ===")
        admin = ensure_user(db, "admin@oil-india.example", "Platform Administrator",
                            UserRole.ADMIN, "+919864000001")
        pm = ensure_user(db, "pm@oil-india.example", "Ananya Baruah",
                         UserRole.PROJECT_MANAGER, "+919864000002")
        sup = ensure_user(db, "supervisor@oil-india.example", "Rakesh Gogoi",
                          UserRole.SITE_SUPERVISOR, "+919864000003")
        sup2 = ensure_user(db, "supervisor2@oil-india.example", "Imran Hussain",
                           UserRole.SITE_SUPERVISOR, "+919864000004")
        db.commit()

        members = [(admin, UserRole.ADMIN), (pm, UserRole.PROJECT_MANAGER),
                   (sup, UserRole.SITE_SUPERVISOR), (sup2, UserRole.SITE_SUPERVISOR)]

        print("\n=== 3. projects ===")
        main_p = make_project(
            db, code="OIL-PL-02", name="Pipeline PL-02 Expansion",
            description="220 km cross-country pipeline expansion across Upper Assam, "
                        "executed in four spreads from Duliajan to Numaligarh.",
            client="Oil India Limited", location="Duliajan, Assam",
            status=ProjectStatus.ACTIVE,
            start=date(2026, 1, 5), finish=date(2026, 12, 18),
            owner=admin, members=members)
        second = make_project(
            db, code="OIL-GGS-07", name="GGS-07 Gas Gathering Station",
            description="New gas gathering station with associated flowlines and "
                        "instrumentation.",
            client="Oil India Limited", location="Moran, Assam",
            status=ProjectStatus.PLANNING,
            start=date(2026, 6, 1), finish=date(2027, 3, 31),
            owner=admin, members=[(admin, UserRole.ADMIN), (pm, UserRole.PROJECT_MANAGER)])
        third = make_project(
            db, code="ML3-PH1", name="Metro Line 3 Phase 1",
            description="Underground metro tunnelling and station civil works.",
            client="MMRC", location="Mumbai",
            status=ProjectStatus.ACTIVE,
            start=date(2026, 3, 1), finish=date(2027, 8, 30),
            owner=admin, members=[(admin, UserRole.ADMIN), (sup2, UserRole.SITE_SUPERVISOR)])
        db.commit()
        log(f"{main_p.code}, {second.code}, {third.code}")

        print("\n=== 4. baseline through the real schedule parser ===")
        rows, leaves = build_pipeline_baseline()
        sched = ScheduleService(db).create(
            main_p.id, ScheduleCreate(name="Baseline Rev 0", description="As-tendered baseline"),
            admin, CTX)
        summary = ScheduleParser(db, sched).parse_file(
            rows_to_csv(rows), "PL02_baseline.csv", MAPPING)
        db.commit()
        log(f"rows read {summary.as_dict().get('rows_read')} → "
            f"{db.query(Activity).filter(Activity.schedule_id == sched.id).count()} activities")

        print("\n=== 5. field reports through the document pipeline ===")
        cutoff = min(today, date(2026, 9, 14))
        docs = build_dpr_documents(leaves, cutoff)
        docs += build_whatsapp_documents(leaves, cutoff)
        docs.append(build_voice_document(leaves, cutoff))
        log(f"generated {len(docs)} documents up to {cutoff}")
        n = ingest(db, main_p.id, sup, docs)
        db.commit()
        parsed = db.query(ProgressReport).filter(ProgressReport.project_id == main_p.id).count()
        log(f"uploaded {n}, parsed into {parsed} progress reports")

        print("\n=== 6. AI matching (real matcher) ===")
        match_svc = MatchingService(db)
        result = match_svc.run(main_p.id, MatchRunRequest(schedule_id=sched.id), admin, CTX)
        db.commit()
        log(f"extracted {result.items_extracted} · auto {result.auto_matched} · "
            f"review {result.needs_review} · unmatched {result.unmatched}")

        print("\n=== 7. confirming the review queue ===")
        pending = db.execute(
            select(ActivityMatch).where(
                ActivityMatch.project_id == main_p.id,
                ActivityMatch.status == MatchStatus.NEEDS_REVIEW,
            )
        ).scalars().all()
        confirmed = 0
        for m in pending:
            if m.candidates and m.score >= 0.62:
                try:
                    match_svc.review(
                        main_p.id, m.id,
                        MatchReviewDecision(decision="confirm"), pm, CTX)
                    confirmed += 1
                except Exception as exc:  # noqa: BLE001
                    log(f"review skipped for {m.id}: {str(exc)[:70]}")
        db.commit()
        log(f"confirmed {confirmed} of {len(pending)} queued matches")

        print("\n=== 8. booking progress (real roll-up) ===")
        applied = ProgressService(db).apply_confirmed_matches(main_p, sched.id, admin, CTX)
        db.commit()
        log(f"created {applied.records_created} · updated {applied.records_updated} · "
            f"skipped undated {applied.skipped_missing_event_date} · "
            f"not-an-event {applied.skipped_not_an_actual_event}")

        print("\n=== 9. delay model ===")
        pred = PredictionService(db)
        outcome = pred.train_model(main_p, TrainRequest(), admin, CTX)
        db.commit()
        if outcome.trained:
            roc = getattr(outcome.metrics, "roc_auc", None) if outcome.metrics else None
            log(f"promoted {outcome.version} — ROC AUC {roc} "
                f"vs baseline {outcome.baseline_roc_auc}")
        else:
            log(f"no model promoted — {outcome.detail}")

        run = pred.run(main_p, sched.id, PredictRequest(), admin, CTX)
        db.commit()
        log(f"scored {run.activities_scored} activities via {run.method}")

        print("\n=== 10. generated reports ===")
        from app.core.constants import GeneratedReportFormat
        from app.services.reporting import ReportService
        rep = ReportService(db)
        for rtype, fmt in [("progress_summary", GeneratedReportFormat.PDF),
                           ("delay_risk", GeneratedReportFormat.PDF),
                           ("executive_overview", GeneratedReportFormat.PDF)]:
            try:
                r = rep.generate_report(main_p.id, rtype, fmt,
                                        {"schedule_id": str(sched.id)}, admin)
                db.commit()
                log(f"{rtype}: {r.status}")
            except Exception as exc:  # noqa: BLE001
                db.rollback()
                log(f"{rtype} failed: {str(exc)[:90]}")

        print("\n=== summary ===")
        for model in (Project, Schedule, Activity, UploadedFile, ProgressReport,
                      ExtractedActivity, ActivityMatch, ActualProgress,
                      DelayPrediction, DelayModelVersion, GeneratedReport):
            print(f"  {db.query(model).count():>6}  {model.__name__}")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
