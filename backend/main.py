from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship
from sqlalchemy import event
from datetime import datetime
from typing import Optional, List
import os

# 1. 数据库配置
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/ledger.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# M4 Mac 优化: 开启 WAL 模式
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. 定义数据库模型
class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True) # 账户名，如"招商银行"
    type = Column(String) # 账户类型，如 "现金", "信用卡"

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime)
    type = Column(String) # "EXPENSE" (支出), "INCOME" (收入), "TRANSFER" (转账)
    amount = Column(Float)
    category = Column(String)
    note = Column(String, nullable=True)
    
    # 关联账户
    account_id = Column(Integer, ForeignKey("accounts.id")) # 主账户（支出方/收入方/转出方）
    target_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True) # 目标账户（仅转账时用）

    # 建立关联关系，方便查询
    account = relationship("Account", foreign_keys=[account_id])
    target_account = relationship("Account", foreign_keys=[target_account_id])

# 创建表
Base.metadata.create_all(bind=engine)

# 3. Pydantic 模型 (用于数据验证)
class AccountCreate(BaseModel):
    name: str
    type: str

class AccountOut(AccountCreate):
    id: int
    class Config:
        orm_mode = True

class TransactionCreate(BaseModel):
    date: datetime
    type: str # EXPENSE, INCOME, TRANSFER
    amount: float
    category: str = "转账" # 转账时默认分类
    note: str = None
    account_id: int
    target_account_id: Optional[int] = None

class TransactionOut(TransactionCreate):
    id: int
    account_name: str
    target_account_name: Optional[str] = None
    class Config:
        orm_mode = True

# 4. FastAPI 实例
app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- API 路由 ---

# 账户管理
@app.get("/api/accounts", response_model=List[AccountOut])
def read_accounts(db: Session = Depends(get_db)):
    return db.query(Account).all()

@app.post("/api/accounts", response_model=AccountOut)
def create_account(account: AccountCreate, db: Session = Depends(get_db)):
    db_account = Account(name=account.name, type=account.type)
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account

# 交易管理
@app.get("/api/transactions", response_model=List[TransactionOut])
def read_transactions(db: Session = Depends(get_db)):
    # 联表查询，获取账户名称
    results = db.query(Transaction).order_by(Transaction.date.desc()).all()
    # 手动组装返回数据，因为 Pydantic ORM 模式在复杂关联下有时需要辅助
    output = []
    for t in results:
        t_out = TransactionOut.from_orm(t)
        t_out.account_name = t.account.name if t.account else "未知账户"
        t_out.target_account_name = t.target_account.name if t.target_account else None
        output.append(t_out)
    return output

@app.post("/api/transactions", response_model=TransactionOut)
def create_transaction(item: TransactionCreate, db: Session = Depends(get_db)):
    # 验证逻辑
    if item.type == "TRANSFER":
        if not item.target_account_id:
            raise HTTPException(status_code=400, detail="转账必须选择转入账户")
        if item.account_id == item.target_account_id:
            raise HTTPException(status_code=400, detail="转出和转入账户不能相同")
            
    db_item = Transaction(**item.dict())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    
    # 重新加载以获取关联对象
    output = TransactionOut.from_orm(db_item)
    output.account_name = db.query(Account).get(item.account_id).name
    if item.target_account_id:
        output.target_account_name = db.query(Account).get(item.target_account_id).name
    return output

@app.delete("/api/transactions/{transaction_id}")
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if transaction is None:
        raise HTTPException(status_code=404, detail="未找到该记录")
    db.delete(transaction)
    db.commit()
    return {"message": "删除成功"}