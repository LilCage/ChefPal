/**
 * 当前 TabBar 激活项索引（0百科 1厨房 2发现 3我的）。
 * 各 Tab 页 onShow 时写入，custom-tab-bar 订阅以高亮当前项。
 */
import { create } from 'zustand'

interface TabState {
  index: number
  setIndex: (index: number) => void
}

export const useTabStore = create<TabState>((set) => ({
  index: 0,
  setIndex: (index) => set({ index }),
}))
