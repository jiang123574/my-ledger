<script setup>
import { ref, onMounted } from 'vue'

const transactions = ref([])
const form = ref({ amount: '', category: '', note: '' }) // amount 改为空字符串以免显示默认0

// 1. 获取数据
const fetchTransactions = async () => {
  const res = await fetch('/api/transactions')
  transactions.value = await res.json()
}

// 2. 提交数据
const submit = async () => {
  if (!form.value.amount || !form.value.category) {
    alert('请输入金额和分类')
    return
  }

  await fetch('/api/transactions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(form.value)
  })
  
  form.value = { amount: '', category: '', note: '' } // 重置表单
  await fetchTransactions() // 刷新列表
}

// 3. 新增：删除功能
const deleteTransaction = async (id) => {
  // 添加一个简单的确认框防止手滑
  if (!confirm('确定要删除这条记录吗？')) return

  try {
    const res = await fetch(`/api/transactions/${id}`, {
      method: 'DELETE'
    })
    
    if (res.ok) {
      // 删除成功后，重新获取列表
      await fetchTransactions()
    } else {
      alert('删除失败，请稍后重试')
    }
  } catch (error) {
    console.error('删除出错:', error)
    alert('网络错误')
  }
}

onMounted(fetchTransactions)
</script>

<template>
  <div style="max-width: 600px; margin: 0 auto; padding: 20px; font-family: sans-serif;">
    <h1 style="text-align: center;">💰 我的记账本</h1>
    
    <div style="margin-bottom: 20px; border: 1px solid #ddd; padding: 20px; border-radius: 8px; background: #f9f9f9;">
      <h3>📝 记一笔</h3>
      <div style="display: flex; gap: 10px; margin-bottom: 10px;">
        <input v-model="form.amount" type="number" placeholder="金额 (¥)" style="flex: 1; padding: 8px;" />
        <input v-model="form.category" type="text" placeholder="分类 (如: 餐饮)" style="flex: 1; padding: 8px;" />
      </div>
      <input v-model="form.note" type="text" placeholder="备注 (可选)" style="width: 100%; padding: 8px; box-sizing: border-box; margin-bottom: 10px;" />
      <button @click="submit" style="width: 100%; padding: 10px; background-color: #4CAF50; color: white; border: none; border-radius: 4px; cursor: pointer;">保存</button>
    </div>

    <ul style="list-style: none; padding: 0;">
      <li v-for="t in transactions" :key="t.id" style="border-bottom: 1px solid #eee; padding: 10px 0; display: flex; justify-content: space-between; align-items: center;">
        
        <div>
          <span style="font-weight: bold; font-size: 1.1em;">{{ t.category }}</span>
          <span style="color: #666; font-size: 0.9em; margin-left: 8px;">{{ t.note }}</span>
          <div style="color: #e67e22; font-weight: bold;">¥ {{ t.amount }}</div>
        </div>

        <button 
          @click="deleteTransaction(t.id)" 
          style="background-color: #ff4444; color: white; border: none; padding: 5px 10px; border-radius: 4px; cursor: pointer; font-size: 0.8em;"
        >
          删除
        </button>

      </li>
    </ul>
    
    <div v-if="transactions.length === 0" style="text-align: center; color: #999; margin-top: 20px;">
      还没有账目，快记一笔吧！
    </div>
  </div>
</template>