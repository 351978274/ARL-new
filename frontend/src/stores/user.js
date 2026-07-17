import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useUserStore = defineStore('user', () => {
  const token = ref(localStorage.getItem('arl_token') || '')
  const username = ref(localStorage.getItem('arl_username') || '')
  const userType = ref(localStorage.getItem('arl_usertype') || '')

  function setLogin(data) {
    token.value = data.token
    username.value = data.username
    userType.value = data.type || 'login'
    localStorage.setItem('arl_token', data.token)
    localStorage.setItem('arl_username', data.username)
    localStorage.setItem('arl_usertype', data.type || 'login')
  }

  function logout() {
    token.value = ''
    username.value = ''
    userType.value = ''
    localStorage.removeItem('arl_token')
    localStorage.removeItem('arl_username')
    localStorage.removeItem('arl_usertype')
  }

  return { token, username, userType, setLogin, logout }
})
