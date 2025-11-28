from fastapi import FastAPI, HTTPException, Depends
from pydantic import BaseModel
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, ForeignKey, or_
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship, backref
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
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# 2. 定义数据库模型
class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    type = Column(String) # EXPENSE / INCOME
    
    # 新增：父分类ID (自关联)
    parent_id = Column(Integer, ForeignKey('categories.id', ondelete="CASCADE"), nullable=True)
    
    # 建立关系：children 获取子分类, parent 获取父分类
    children = relationship("Category", 
                            backref=backref('parent', remote_side=[id]),
                            cascade="all, delete")

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    type = Column(String)
    initial_balance = Column(Float, default=0.0)
    billing_day = Column(Integer, nullable=True)
    due_day = Column(Integer, nullable=True)

    sent_transactions = relationship("Transaction", foreign_keys="Transaction.account_id", back_populates="account", cascade="all, delete")
    received_transactions = relationship("Transaction", foreign_keys="Transaction.target_account_id", back_populates="target_account", cascade="all, delete")

    @property
    def balance(self):
        current = self.initial_balance
        for t in self.sent_transactions:
            if t.type == 'INCOME': current += t.amount
            elif t.type == 'EXPENSE': current -= t.amount
            elif t.type == 'TRANSFER': current -= t.amount
        for t in self.received_transactions:
            if t.type == 'TRANSFER': current += t.amount
        return round(current, 2)

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime)
    type = Column(String)
    amount = Column(Float)
    category = Column(String) # 这里存的是分类名称 (为了简单报表), 实际项目建议存 category_id
    note = Column(String, nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"))
    target_account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True)

    account = relationship("Account", foreign_keys=[account_id], back_populates="sent_transactions", lazy='joined')
    target_account = relationship("Account", foreign_keys=[target_account_id], back_populates="received_transactions", lazy='joined')

    @property
    def account_name(self): return self.account.name if self.account else "未知账户"
    @property
    def target_account_name(self): return self.target_account.name if self.target_account else None

Base.metadata.create_all(bind=engine)

# 3. Pydantic 模型
class CategoryCreate(BaseModel):
    name: str
    type: str
    parent_id: Optional[int] = None # 新增

class CategoryUpdate(BaseModel):
    name: str
    type: str
    parent_id: Optional[int] = None

class CategoryOut(CategoryCreate):
    id: int
    class Config: from_attributes = True

class AccountCreate(BaseModel):
    name: str
    type: str
    initial_balance: float = 0.0
    billing_day: Optional[int] = None
    due_day: Optional[int] = None

class AccountUpdate(AccountCreate): pass

class AccountOut(AccountCreate):
    id: int
    balance: float
    class Config: from_attributes = True

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
    class Config: from_attributes = True

# 4. FastAPI
app = FastAPI()

def get_db():
    db = SessionLocal(); try: yield db; finally: db.close()

def init_default_categories():
    db = SessionLocal()
    if db.query(Category).count() == 0:
        # 预设带子分类的数据结构
        data = [
            {"name": "餐饮", "type": "EXPENSE", "children": ["早餐", "午餐", "晚餐", "饮料"]},
            {"name": "交通", "type": "EXPENSE", "children": ["地铁", "公交", "打车", "加油"]},
            {"name": "购物", "type": "EXPENSE", "children": ["服饰", "日用", "电子"]},
            {"name": "工资", "type": "INCOME", "children": []},
            {"name": "理财", "type": "INCOME", "children": []}
        ]
        for item in data:
            parent = Category(name=item["name"], type=item["type"])
            db.add(parent)
            db.commit() # 提交以获取 parent.id
            db.refresh(parent)
            for child_name in item["children"]:
                db.add(Category(name=child_name, type=item["type"], parent_id=parent.id))
        db.commit()
    db.close()

init_default_categories()

# --- API ---
@app.get("/api/categories", response_model=List[CategoryOut])
def read_categories(db: Session = Depends(get_db)):
    return db.query(Category).all()

@app.post("/api/categories", response_model=CategoryOut)
def create_category(category: CategoryCreate, db: Session = Depends(get_db)):
    db_obj = Category(name=category.name, type=category.type, parent_id=category.parent_id)
    db.add(db_obj)
    db.commit()
    db.refresh(db_obj)
    return db_obj

# 新增：修改分类
@app.put("/api/categories/{id}", response_model=CategoryOut)
def update_category(id: int, cat: CategoryUpdate, db: Session = Depends(get_db)):
    db_obj = db.query(Category).filter(Category.id == id).first()
    if not db_obj: raise HTTPException(404, "分类不存在")
    db_obj.name = cat.name
    db_obj.type = cat.type
    db_obj.parent_id = cat.parent_id
    db.commit()
    db.refresh(db_obj)
    return db_obj

@app.delete("/api/categories/{id}")
def delete_category(id: int, db: Session = Depends(get_db)):
    obj = db.query(Category).filter(Category.id == id).first()
    if obj: db.delete(obj); db.commit()
    return {"ok": True}

@app.get("/api/accounts", response_model=List[AccountOut])
def read_accounts(db: Session = Depends(get_db)): return db.query(Account).all()

@app.post("/api/accounts", response_model=AccountOut)
def create_account(acc: AccountCreate, db: Session = Depends(get_db)):
    db_obj = Account(**acc.dict()); db.add(db_obj); db.commit(); db.refresh(db_obj); return db_obj

@app.put("/api/accounts/{id}", response_model=AccountOut)
def update_account(id: int, acc: AccountUpdate, db: Session = Depends(get_db)):
    db_obj = db.query(Account).filter(Account.id == id).first()
    if not db_obj: raise HTTPException(404, "账户不存在")
    for k, v in acc.dict().items(): setattr(db_obj, k, v)
    db.commit(); db.refresh(db_obj); return db_obj

@app.delete("/api/accounts/{id}")
def delete_account(id: int, db: Session = Depends(get_db)):
    obj = db.query(Account).filter(Account.id == id).first()
    if obj: db.delete(obj); db.commit()
    return {"ok": True}

@app.get("/api/transactions", response_model=List[TransactionOut])
def read_transactions(account_id: Optional[int]=None, db: Session=Depends(get_db)):
    q = db.query(Transaction)
    if account_id: q = q.filter(or_(Transaction.account_id==account_id, Transaction.target_account_id==account_id))
    return q.order_by(Transaction.date.desc()).all()

@app.post("/api/transactions", response_model=TransactionOut)
def create_transaction(item: TransactionCreate, db: Session = Depends(get_db)):
    if item.type == "TRANSFER":
        if not item.target_account_id: raise HTTPException(400, "需转入账户")
        if item.account_id == item.target_account_id: raise HTTPException(400, "账户不能相同")
    db_item = Transaction(**item.dict())
    db.add(db_item)
    db.commit()
    db.refresh(db_item)
    return db_item

@app.delete("/api/transactions/{transaction_id}")
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    obj = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if obj: db.delete(obj); db.commit()
    return {"ok": True}