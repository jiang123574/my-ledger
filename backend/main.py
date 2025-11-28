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
    name = Column(String, unique=True, index=True)
    type = Column(String)
    # 新增：初始余额 (默认为 0)
    initial_balance = Column(Float, default=0.0)

    # 反向关联：找到所有以该账户为主体(account_id)的交易
    # dynamic 让我们可以像查询一样过滤它们，但在计算余额时我们直接遍历列表
    sent_transactions = relationship("Transaction", foreign_keys="Transaction.account_id", back_populates="account")
    
    # 反向关联：找到所有转入该账户(target_account_id)的交易
    received_transactions = relationship("Transaction", foreign_keys="Transaction.target_account_id", back_populates="target_account")

    # --- 核心逻辑：实时计算余额 ---
    @property
    def balance(self):
        current = self.initial_balance
        
        # 1. 处理作为“主账户”的交易
        for t in self.sent_transactions:
            if t.type == 'INCOME':
                current += t.amount
            elif t.type == 'EXPENSE':
                current -= t.amount
            elif t.type == 'TRANSFER':
                current -= t.amount # 转出扣钱
        
        # 2. 处理作为“目标账户”的交易 (只有转账)
        for t in self.received_transactions:
            if t.type == 'TRANSFER':
                current += t.amount # 转入加钱
                
        return round(current, 2) # 保留两位小数

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime)
    type = Column(String) # EXPENSE, INCOME, TRANSFER
    amount = Column(Float)
    category = Column(String)
    note = Column(String, nullable=True)
    
    account_id = Column(Integer, ForeignKey("accounts.id"))
    target_account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)

    # 关联关系 (添加 back_populates 以支持双向关联)
    account = relationship("Account", foreign_keys=[account_id], back_populates="sent_transactions", lazy='joined')
    target_account = relationship("Account", foreign_keys=[target_account_id], back_populates="received_transactions", lazy='joined')

    @property
    def account_name(self):
        return self.account.name if self.account else "未知账户"

    @property
    def target_account_name(self):
        return self.target_account.name if self.target_account else None

# 创建表
Base.metadata.create_all(bind=engine)

# 3. Pydantic 模型
class AccountCreate(BaseModel):
    name: str
    type: str
    initial_balance: float = 0.0 # 新增字段

class AccountOut(AccountCreate):
    id: int
    balance: float # 返回给前端的计算后的余额
    class Config:
        from_attributes = True

class TransactionCreate(BaseModel):
    date: datetime
    type: str
    amount: float
    category: str = "转账"
    note: str = None
    account_id: int
    target_account_id: Optional[int] = None

class TransactionOut(TransactionCreate):
    id: int
    account_name: str
    target_account_name: Optional[str] = None
    class Config:
        from_attributes = True

# 4. FastAPI 实例
app = FastAPI()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- API 路由 ---

@app.get("/api/accounts", response_model=List[AccountOut])
def read_accounts(db: Session = Depends(get_db)):
    # 获取所有账户，SQLAlchemy 会自动通过 @property balance 计算结果
    return db.query(Account).all()

@app.post("/api/accounts", response_model=AccountOut)
def create_account(account: AccountCreate, db: Session = Depends(get_db)):
    db_account = Account(
        name=account.name, 
        type=account.type,
        initial_balance=account.initial_balance
    )
    db.add(db_account)
    db.commit()
    db.refresh(db_account)
    return db_account

@app.get("/api/transactions", response_model=List[TransactionOut])
def read_transactions(db: Session = Depends(get_db)):
    return db.query(Transaction).order_by(Transaction.date.desc()).all()

@app.post("/api/transactions", response_model=TransactionOut)
def create_transaction(item: TransactionCreate, db: Session = Depends(get_db)):
    if item.type == "TRANSFER":
        if not item.target_account_id:
            raise HTTPException(status_code=400, detail="转账必须选择转入账户")
        if item.account_id == item.target_account_id:
            raise HTTPException(status_code=400, detail="转出和转入账户不能相同")
            
    db_item = Transaction(**item.dict())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@app.delete("/api/transactions/{transaction_id}")
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    transaction = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if transaction is None:
        raise HTTPException(status_code=404, detail="未找到该记录")
    db.delete(transaction)
    db.commit()
    return {"message": "删除成功"}