// 适老化大字模式：存本地，所有页面 onShow 时读取并挂到根节点 class 上
const KEY = 'fontLarge';

const isLarge = () => !!wx.getStorageSync(KEY);
const fontClass = () => (isLarge() ? 'font-lg' : '');
const setLarge = v => wx.setStorageSync(KEY, !!v);
const toggle = () => {
  const v = !isLarge();
  setLarge(v);
  return v;
};

module.exports = { isLarge, fontClass, setLarge, toggle };
