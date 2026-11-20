import time, json
from sqlalchemy import select, func
from src.config.database import Session
from migrations.initial import migrate
from src.models import User, Dataset, Job, Report, Delivery, Audit, GroupMembership, ReportGroup
from src.services.business import metadata, seed_records, analyze
from src.services.reports import deliver
from src.utils.security import hash_password
from src.utils.serialization import checksum

DEMO_USERS = [
    ('admin', '林知 · 业务负责人', '业务复核组', True),
    ('analyst', '陈舟 · 分析员', '中窑班', True),
    ('viewer', '周禾 · 观察员', '西窑班', False),
    ('east', '张师傅 · 东窑班长', '东窑班', True),
    ('west', '王师傅 · 西窑班长', '西窑班', True),
]
GROUPS = ['东窑班', '中窑班', '西窑班']


def seed():
    migrate()
    with Session() as db:
        for account, name, group, leader in DEMO_USERS:
            email = account + '@demo.local'
            role = account if account in ('admin', 'analyst', 'viewer') else 'viewer'
            user = db.scalar(select(User).where(User.email == email))
            if not user:
                user = User(email=email, name=name, role=role, password=hash_password('Demo123!'))
                db.add(user)
                db.flush()
            if not db.scalar(select(GroupMembership).where(GroupMembership.user_id == user.id,
                                                          GroupMembership.group_name == group)):
                db.add(GroupMembership(user_id=user.id, group_name=group, is_leader=leader))
        db.flush()
        m = metadata()
        d = db.scalar(select(Dataset).where(Dataset.name == m['dataset_name']))
        if not d:
            rows = seed_records()
            d = Dataset(name=m['dataset_name'], source=m['short'] + '-202611.csv', records=rows,
                        checksum=checksum(rows), created_at=time.time())
            db.add(d)
            db.flush()
        if not db.scalar(select(Job).where(Job.name == '基线复核 · ' + m['name'])):
            params = {p['key']: p['default'] for p in m.get('parameters', [])}
            result = analyze(d.records, params)
            json.dumps(result, ensure_ascii=False, allow_nan=False)
            admin = db.scalar(select(User).where(User.role == 'admin'))
            j = Job(name='基线复核 · ' + m['name'], dataset_id=d.id, params=params, status='completed',
                    result=result, created_by=admin.id, created_at=time.time() - 3600,
                    finished_at=time.time() - 3595, approved=True)
            db.add(j)
            db.flush()
            r = Report(name='每日业务复核简报', job_id=j.id, destination='东窑班 · 中窑班 · 西窑班',
                       interval_seconds=86400, next_run=time.time() + 86400, enabled=True)
            db.add(r)
            db.flush()
            for group in GROUPS:
                db.add(ReportGroup(report_id=r.id, name=group))
            db.flush()
            deliver(db, r)
            db.add(Audit(actor='seed', action='demo.baseline', detail={'dataset': d.id}, at=time.time()))
        db.commit()
        counts = {model.__tablename__: db.scalar(select(func.count()).select_from(model))
                  for model in [User, Dataset, Job, Report, Delivery, Audit, GroupMembership, ReportGroup]}
        print(json.dumps(counts, ensure_ascii=False))
        return counts


if __name__ == '__main__':
    seed()
