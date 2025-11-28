<script setup>
import { ref, onMounted } from 'vue'

const transactions = ref([])
const form = ref({ amount: 0, category: '', note: '' })

// 获取数据
const fetchTransactions = async () => {
  const res = await fetch('/api/transactions')
  transactions.value = await res.json()
}

// 提交数据
const submit = async () => {
  await fetch('/api/transactions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(form.value)
  })
  form.value = { amount: 0, category: '', note: '' } // 重置表单
  await fetchTransactions() // 刷新列表
}

onMounted(fetchTransactions)
</script>

<template>
  <div style="padding: 20px; font-family: sans-serif;">
    <h1>💰 我的记账本</h1>
    
    <div style="margin-bottom: 20px; border: 1px solid #ddd; padding: 15px;">
      <h3>记一笔</h3>
      <input v-model="form.amount" type="number" placeholder="金额" />
      <input v-model="form.category" type="text" placeholder="分类 (如: 餐饮)" />
      <input v-model="form.note" type="text" placeholder="备注" />
      <button @click="submit">保存</button>
    </div>

    <ul>
      <li v-for="t in transactions" :key="t.id">
        <strong>{{ t.category }}</strong>: ¥{{ t.amount }} 
        <span style="color: grey">({{ t.note }})</span>
      </li>
    </ul>
  </div>
</template>