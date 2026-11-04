const { BASE_URL } = require('./config');

function request(path, method, data) {
  return new Promise((resolve, reject) => {
    wx.request({
      url: BASE_URL + path,
      method: method || 'GET',
      data: data || {},
      header: { 'content-type': 'application/json' },
      success(res) {
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(res.data);
        } else {
          const detail = res.data && res.data.detail;
          reject(new Error(typeof detail === 'string' ? detail : ('HTTP ' + res.statusCode)));
        }
      },
      fail(err) {
        reject(new Error((err && err.errMsg) || '网络请求失败，请检查后端是否启动'));
      }
    });
  });
}

function upload(path, filePath, formData) {
  return new Promise((resolve, reject) => {
    wx.uploadFile({
      url: BASE_URL + path,
      filePath,
      name: 'file',
      formData: formData || {},
      success(res) {
        let data = res.data;
        try { data = JSON.parse(data); } catch (e) { /* 保留原始文本 */ }
        if (res.statusCode >= 200 && res.statusCode < 300) {
          resolve(data);
        } else {
          const detail = data && data.detail;
          reject(new Error(typeof detail === 'string' ? detail : ('HTTP ' + res.statusCode)));
        }
      },
      fail(err) {
        reject(new Error((err && err.errMsg) || '图片上传失败'));
      }
    });
  });
}

function imgUrl(p) {
  if (!p) return '';
  return /^https?:/i.test(p) ? p : BASE_URL + p;
}

module.exports = { request, upload, imgUrl, BASE_URL };
