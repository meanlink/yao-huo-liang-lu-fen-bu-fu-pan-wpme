import os
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy import select
from src.config.database import get_db
from src.config.settings import ARTIFACT_DIR
from src.models import Report, Delivery, Job, DeliveryVersion
from src.schemas.report import ReportInput, SignInput, CorrectionInput
from src.middlewares.auth import current_user, admin_only
from src.services import reports, briefing
from src.services.audit import record
from src.utils.serialization import report_dict, delivery_dict
router=APIRouter()
@router.get('/reports')
def listing(db=Depends(get_db),u=Depends(current_user)):
    return [{**report_dict(r),'groups':briefing.report_groups(db,r)} for r in db.scalars(select(Report).order_by(Report.id.desc()))]
@router.post('/reports',status_code=201)
def create(data:ReportInput,db=Depends(get_db),u=Depends(admin_only)):
    r=reports.create(db,data); record(db,u.email,'report.schedule',{'id':r.id,'destination':r.destination,'groups':briefing.report_groups(db,r)}); db.commit()
    return report_dict(r)
@router.post('/reports/{id}/toggle')
def toggle(id:int,db=Depends(get_db),u=Depends(admin_only)):
    r=db.get(Report,id)
    if not r:raise HTTPException(404,'分发计划不存在')
    r.enabled=not r.enabled;record(db,u.email,'report.toggle',{'id':id,'enabled':r.enabled});db.commit()
    return report_dict(r)
@router.post('/reports/{id}/corrections')
def correction(id:int,data:CorrectionInput,db=Depends(get_db),u=Depends(admin_only)):
    r=db.get(Report,id)
    if not r:raise HTTPException(404,'分发计划不存在')
    job=db.get(Job,data.job_id)
    delivery,version,groups=reports.correction(db,r,job,data.note)
    record(db,u.email,'report.correction',{'id':id,'delivery':delivery.id,'version':version,'groups':groups})
    db.commit()
    return {'delivery':delivery_dict(delivery),'version':version,'groups':groups,
            'briefing':briefing.briefing_dict(db,r)}
@router.get('/deliveries')
def deliveries(db=Depends(get_db),u=Depends(current_user)):
    versions={dv.delivery_id:dv for dv in db.scalars(select(DeliveryVersion))}
    return [{**delivery_dict(d),'version':versions[d.id].version if d.id in versions else None,
             'channel':versions[d.id].channel if d.id in versions else None}
            for d in db.scalars(select(Delivery).order_by(Delivery.id.desc()).limit(100))]
@router.get('/deliveries/{id}/download')
def download(id:int,format:str='csv',db=Depends(get_db),u=Depends(current_user)):
    d=db.get(Delivery,id)
    if not d:raise HTTPException(404,'归档不存在')
    if format not in ('csv','json'):raise HTTPException(422,'支持 CSV 或 JSON')
    filename=d.filename+('.json' if format=='json' else '')
    p=os.path.join(ARTIFACT_DIR,filename)
    if not os.path.exists(p):raise HTTPException(404,'归档文件不存在，请重新安排分发')
    return FileResponse(p,filename=filename,media_type='application/json' if format=='json' else 'text/csv; charset=utf-8')
@router.post('/deliveries/{id}/sign')
def sign(id:int,data:SignInput,db=Depends(get_db),u=Depends(current_user)):
    row,dv=briefing.sign(db,id,data.group,data.note,u)
    db.commit()
    return {'sign':briefing.sign_dict(row),'version':dv.version,'briefing':briefing.briefing_dict(db,db.get(Report,dv.report_id))}
@router.get('/briefings')
def inbox(db=Depends(get_db),u=Depends(current_user)):
    return briefing.inbox(db,u)
@router.get('/briefings/{id}')
def briefing_detail(id:int,db=Depends(get_db),u=Depends(current_user)):
    return briefing.briefing(db,id,u)
@router.post('/briefings/repair')
def repair(db=Depends(get_db),u=Depends(admin_only)):
    count=briefing.repair(db); record(db,u.email,'briefing.repair',{'created':count}); db.commit()
    return {'created':count}
@router.get('/groups')
def groups(db=Depends(get_db),u=Depends(current_user)):
    return briefing.group_catalog(db)
