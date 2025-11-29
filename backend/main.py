from fastapi import FastAPI, HTTPException, Depends
from contextlib import asynccontextmanager
from pydantic import BaseModel, ConfigDict
from sqlalchemy import create_engine, Column, Integer, String, Numeric, DateTime, ForeignKey, or_, func, case
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session, relationship, backref, aliased
from sqlalchemy import event
from datetime import datetime
from typing import Optional, List
import os
import decimal

# --- 1. 数据库基础配置 ---
# 自动创建数据目录
if not os.path.exists("./data"):
    try:
        os.makedirs("./data")
        print("✅ 已创建 ./data 目录")
    except Exception as e:
        print(f"⚠️ 创建目录失败 (可能是挂载卷): {e}")

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./data/ledger.db")
# check_same_thread=False 是 SQLite 在多线程环境(FastAPI)下的必须配置
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# 开启 SQLite WAL 模式 (提升并发性能) 和 外键约束
@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- 2. 数据库模型定义 (SQLAlchemy) ---

class Category(Base):
    __tablename__ = "categories"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    type = Column(String) # EXPENSE / INCOME
    parent_id = Column(Integer, ForeignKey('categories.id', ondelete="CASCADE"), nullable=True)
    
    # 自关联：支持多级分类
    children = relationship("Category", backref=backref('parent', remote_side=[id]), cascade="all, delete")

class Account(Base):
    __tablename__ = "accounts"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    type = Column(String)
    # 使用 Numeric 替代 Float 避免精度丢失
    initial_balance = Column(Numeric(10, 2), default=0.00)
    billing_day = Column(Integer, nullable=True)
    due_day = Column(Integer, nullable=True)
    
    # 关联交易，级联删除
    sent_transactions = relationship("Transaction", foreign_keys="Transaction.account_id", back_populates="account", cascade="all, delete")
    received_transactions = relationship("Transaction", foreign_keys="Transaction.target_account_id", back_populates="target_account", cascade="all, delete")

class Transaction(Base):
    __tablename__ = "transactions"
    id = Column(Integer, primary_key=True, index=True)
    date = Column(DateTime)
    type = Column(String) # EXPENSE, INCOME, TRANSFER
    amount = Column(Numeric(10, 2))
    category = Column(String)
    tag = Column(String, nullable=True)
    note = Column(String, nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"))
    target_account_id = Column(Integer, ForeignKey("accounts.id", ondelete="CASCADE"), nullable=True)
    
    # [新增] 关联 ID：用于将“支出”和自动生成的“转账”绑定在一起
    link_id = Column(Integer, ForeignKey("transactions.id", ondelete="CASCADE"), nullable=True)

    # 关系定义
    account = relationship("Account", foreign_keys=[account_id], back_populates="sent_transactions", lazy='joined')
    target_account = relationship("Account", foreign_keys=[target_account_id], back_populates="received_transactions", lazy='joined')
    
    # 自关联关系 (例如：访问关联的转账记录)
    linked_transaction = relationship("Transaction", remote_side=[id], backref=backref("parent_transaction", remote_side=[link_id]), cascade="all, delete")

    @property
    def account_name(self): return self.account.name if self.account else "未知账户"
    
    @property
    def target_account_name(self): return self.target_account.name if self.target_account else None

# --- 3. Pydantic 数据模型 (Schema) ---

class CategoryCreate(BaseModel):
    name: str; type: str; parent_id: Optional[int] = None
class CategoryUpdate(BaseModel):
    name: str; type: str; parent_id: Optional[int] = None
class CategoryOut(CategoryCreate):
    id: int
    model_config = ConfigDict(from_attributes=True)

class AccountCreate(BaseModel):
    name: str; type: str; initial_balance: float = 0.0; billing_day: Optional[int] = None; due_day: Optional[int] = None
class AccountUpdate(AccountCreate): pass
class AccountOut(AccountCreate):
    id: int; balance: float # 这里定义为 float 方便前端处理，后端会自动转换 Decimal
    model_config = ConfigDict(from_attributes=True)

class TransactionCreate(BaseModel):
    date: datetime; type: str; amount: float; category: str = "转账"; 
    tag: Optional[str] = None; 
    note: Optional[str] = None; 
    account_id: int; 
    target_account_id: Optional[int] = None
    fund_account_id: Optional[int] = None # 辅助字段：资金来源

class TransactionUpdate(BaseModel):
    date: datetime; type: str; amount: float; category: str; 
    tag: Optional[str] = None; 
    note: Optional[str] = None; 
    account_id: int; 
    target_account_id: Optional[int] = None

class TransactionOut(TransactionCreate):
    id: int; account_name: str; target_account_name: Optional[str] = None
    link_id: Optional[int] = None
    model_config = ConfigDict(from_attributes=True)

# --- 4. 初始化逻辑 ---
def init_db_data():
    """初始化数据库表和默认分类数据"""
    print("🔄 检查数据库初始化...")
    try:
        Base.metadata.create_all(bind=engine)
        print("✅ 数据库表结构确认完毕")

        db = SessionLocal()
        count = db.query(Category).count()
        if count == 0:
            print("📦 写入默认分类数据...")
            data = [
                {"name": "餐饮", "type": "EXPENSE", "children": ["早餐", "午餐", "晚餐", "饮料", "零食"]},
                {"name": "交通", "type": "EXPENSE", "children": ["地铁", "公交", "打车", "加油", "停车"]},
                {"name": "购物", "type": "EXPENSE", "children": ["服饰", "日用", "数码", "美妆"]},
                {"name": "居住", "type": "EXPENSE", "children": ["房租", "水电", "宽带", "物业"]},
                {"name": "工资", "type": "INCOME", "children": []},
                {"name": "理财", "type": "INCOME", "children": ["利息", "基金", "股票"]}
            ]
            for item in data:
                parent = Category(name=item["name"], type=item["type"])
                db.add(parent)
                db.commit()
                db.refresh(parent)
                for child_name in item["children"]:
                    db.add(Category(name=child_name, type=item["type"], parent_id=parent.id))
            db.commit()
            print("✅ 默认分类写入完成")
        db.close()
    except Exception as e:
        print(f"❌ 初始化失败: {e}")

# --- 5. FastAPI 应用配置 ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db_data()
    yield

app = FastAPI(lifespan=lifespan)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# --- 6. API 接口 ---

# === 分类 ===
@app.get("/api/categories", response_model=List[CategoryOut])
def read_categories(db: Session = Depends(get_db)):
    return db.query(Category).all()

@app.post("/api/categories", response_model=CategoryOut)
def create_category(category: CategoryCreate, db: Session = Depends(get_db)):
    db_obj = Category(name=category.name, type=category.type, parent_id=category.parent_id)
    db.add(db_obj); db.commit(); db.refresh(db_obj); return db_obj

@app.put("/api/categories/{id}", response_model=CategoryOut)
def update_category(id: int, cat: CategoryUpdate, db: Session = Depends(get_db)):
    db_obj = db.query(Category).filter(Category.id == id).first()
    if not db_obj: raise HTTPException(404, "分类不存在")
    db_obj.name = cat.name; db_obj.type = cat.type; db_obj.parent_id = cat.parent_id
    db.commit(); db.refresh(db_obj); return db_obj

@app.delete("/api/categories/{id}")
def delete_category(id: int, db: Session = Depends(get_db)):
    obj = db.query(Category).filter(Category.id == id).first()
    if obj: db.delete(obj); db.commit()
    return {"ok": True}

# === 账户 (包含重构后的余额计算) ===
@app.get("/api/accounts", response_model=List[AccountOut])
def read_accounts(db: Session = Depends(get_db)):
    # 性能优化：使用 SQL 聚合计算余额，避免 N+1 查询
    # 逻辑：初始余额 + 流入(INCOME或作为转入方) - 流出(EXPENSE/TRANSFER或作为转出方)
    
    # 1. 计算作为 'account_id' (流出方) 的总和：支出 + 转账(转出)
    sent_sub = db.query(
        Transaction.account_id,
        func.sum(Transaction.amount).label('sent_total')
    ).group_by(Transaction.account_id).subquery()

    # 2. 计算作为 'target_account_id' (流入方) 的总和：转账(转入)
    # 注意：INCOME 类型目前逻辑是记在 account_id 上，但它是流入。
    # 我们需要根据 Transaction.type 来区分正负
    
    # 更通用的 SQL 聚合方案：
    # 余额 = initial_balance 
    #       + SUM(CASE WHEN type='INCOME' AND account_id=me THEN amount ELSE 0 END)
    #       - SUM(CASE WHEN (type='EXPENSE' OR type='TRANSFER') AND account_id=me THEN amount ELSE 0 END)
    #       + SUM(CASE WHEN type='TRANSFER' AND target_account_id=me THEN amount ELSE 0 END)
    
    accounts = db.query(Account).all()
    results = []
    
    # 这种方式比纯 Python 循环快，但不如纯 SQL 快。考虑到 SQLite 对复杂 CASE 聚合的支持，
    # 我们可以先查出所有 Account 对象，然后用一个高效的聚合查询查出所有交易并在此处合并，
    # 或者对于小规模个人记账，保持简单逻辑但优化查询次数。
    
    # 这里采用“一次性查出所有交易汇总”的中间方案，比 N+1 快得多
    
    # 查出每个账户作为发起方的统计 (区分 INCOME 和 其他)
    from_stats = db.query(
        Transaction.account_id,
        Transaction.type,
        func.sum(Transaction.amount)
    ).group_by(Transaction.account_id, Transaction.type).all()
    
    # 查出每个账户作为接收方的统计 (TRANSFER)
    to_stats = db.query(
        Transaction.target_account_id,
        func.sum(Transaction.amount)
    ).filter(Transaction.type == 'TRANSFER').group_by(Transaction.target_account_id).all()
    
    # 内存中合并数据
    balance_map = {a.id: a.initial_balance for a in accounts}
    
    for acc_id, type_, amt in from_stats:
        if not acc_id: continue
        if type_ == 'INCOME':
            balance_map[acc_id] += amt
        else: # EXPENSE, TRANSFER (作为发起方是减)
            balance_map[acc_id] -= amt
            
    for acc_id, amt in to_stats:
        if not acc_id: continue
        balance_map[acc_id] += amt # 作为接收方是加
        
    for acc in accounts:
        # 临时将计算好的余额赋给对象，以便 Pydantic 序列化
        acc.balance = balance_map.get(acc.id, 0)
        results.append(acc)
        
    return results

@app.post("/api/accounts", response_model=AccountOut)
def create_account(acc: AccountCreate, db: Session = Depends(get_db)):
    db_obj = Account(**acc.model_dump())
    db.add(db_obj); db.commit(); db.refresh(db_obj)
    db_obj.balance = db_obj.initial_balance # 新账户余额即初始余额
    return db_obj

@app.put("/api/accounts/{id}", response_model=AccountOut)
def update_account(id: int, acc: AccountUpdate, db: Session = Depends(get_db)):
    db_obj = db.query(Account).filter(Account.id == id).first()
    if not db_obj: raise HTTPException(404, "账户不存在")
    for k, v in acc.model_dump().items(): setattr(db_obj, k, v)
    db.commit(); db.refresh(db_obj)
    # 简单处理：更新后返回的余额可能不准，建议前端重新拉取列表，或此处重新计算(略)
    # 为保持一致性，这里暂时返回初始余额作为balance占位，实际前端通常会刷新列表
    db_obj.balance = db_obj.initial_balance 
    return db_obj

@app.delete("/api/accounts/{id}")
def delete_account(id: int, db: Session = Depends(get_db)):
    obj = db.query(Account).filter(Account.id == id).first()
    if obj: db.delete(obj); db.commit()
    return {"ok": True}

# === 交易 (修复核心逻辑) ===
@app.get("/api/transactions", response_model=List[TransactionOut])
def read_transactions(account_id: Optional[int] = None, db: Session = Depends(get_db)):
    q = db.query(Transaction)
    if account_id:
        q = q.filter(or_(Transaction.account_id == account_id, Transaction.target_account_id == account_id))
    return q.order_by(Transaction.date.desc()).all()

@app.post("/api/transactions", response_model=TransactionOut)
def create_transaction(item: TransactionCreate, db: Session = Depends(get_db)):
    # 1. 转账校验
    if item.type == "TRANSFER":
        if not item.target_account_id: raise HTTPException(400, "需转入账户")
        if item.account_id == item.target_account_id: raise HTTPException(400, "账户不能相同")
    
    # 2. 资金联动校验
    if item.type == "EXPENSE" and item.fund_account_id:
        if item.account_id == item.fund_account_id: raise HTTPException(400, "支出账户和资金账户不能相同")

    # 3. 创建主交易
    db_item = Transaction(
        date=item.date,
        type=item.type,
        amount=item.amount,
        category=item.category,
        tag=item.tag,
        note=item.note,
        account_id=item.account_id,
        target_account_id=item.target_account_id
    )
    
    db.add(db_item)
    db.flush() # 关键：先 flush 以获取 db_item.id，但不提交事务

    # 4. 处理资金联动 (自动生成转账)
    if item.type == "EXPENSE" and item.fund_account_id:
        # 自动创建转账：资金账户 -> 支出账户
        transfer_item = Transaction(
            date=item.date, 
            type="TRANSFER", 
            amount=item.amount,
            category="转账", 
            account_id=item.fund_account_id, 
            target_account_id=item.account_id,
            note=f"自动转账 (用于: {item.category})",
            link_id=db_item.id # 绑定主交易ID
        )
        db.add(transfer_item)

    db.commit()
    db.refresh(db_item)
    return db_item

@app.put("/api/transactions/{id}", response_model=TransactionOut)
def update_transaction(id: int, item: TransactionUpdate, db: Session = Depends(get_db)):
    db_item = db.query(Transaction).filter(Transaction.id == id).first()
    if not db_item: raise HTTPException(404, "记录不存在")
    
    if item.type == "TRANSFER":
        if not item.target_account_id: raise HTTPException(400, "需转入账户")
        if item.account_id == item.target_account_id: raise HTTPException(400, "账户不能相同")

    # 更新字段
    db_item.date = item.date
    db_item.type = item.type
    db_item.amount = item.amount
    db_item.category = item.category
    db_item.tag = item.tag
    db_item.note = item.note
    db_item.account_id = item.account_id
    db_item.target_account_id = item.target_account_id
    
    # 可以在这里增加逻辑：如果这是一个被绑定的主交易，同步更新关联转账的金额/时间
    # 但为了逻辑简单，暂不自动更新关联转账（这需要复杂的业务判断）
    
    db.commit()
    db.refresh(db_item)
    return db_item

@app.delete("/api/transactions/{transaction_id}")
def delete_transaction(transaction_id: int, db: Session = Depends(get_db)):
    # 查找记录
    obj = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if obj:
        # 修复逻辑：如果有其他记录 link_id 指向当前记录（即当前是主记录），则一并删除关联记录
        linked_objs = db.query(Transaction).filter(Transaction.link_id == transaction_id).all()
        for linked in linked_objs:
            db.delete(linked)
        
        # 正常删除当前记录
        db.delete(obj)
        db.commit()
    return {"ok": True}