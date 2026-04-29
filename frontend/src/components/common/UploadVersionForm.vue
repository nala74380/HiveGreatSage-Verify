<template>
  <el-form :model="form" :rules="rules" ref="formRef" label-width="90px" @submit.prevent>
    <el-form-item label="版本号" prop="version">
      <el-input
        v-model="form.version"
        placeholder="如：1.0.1"
        style="width:160px"
      />
      <span class="field-hint" style="margin-left:8px">格式：MAJOR.MINOR.PATCH</span>
    </el-form-item>

    <el-form-item label="强制更新">
      <el-switch v-model="form.force_update" />
      <span class="field-hint" style="margin-left:8px">
        {{ form.force_update ? '开启：客户端不更新则无法运行' : '关闭：提示但可跳过' }}
      </span>
    </el-form-item>

    <el-form-item label="更新说明">
      <el-input
        v-model="form.release_notes"
        type="textarea"
        :rows="2"
        placeholder="选填，如：修复找图精度问题，优化内存占用"
        style="width:100%"
      />
    </el-form-item>

    <el-form-item label="选择文件" prop="file">
      <div class="upload-area">
        <input
          ref="fileInput"
          type="file"
          :accept="clientType === 'pc' ? '.zip,.exe' : '.lrj,.apk'"
          style="display:none"
          @change="onFileChange"
        />
        <el-button @click="fileInput.click()" :icon="Upload">
          {{ form.file ? form.file.name : '点击选择文件' }}
        </el-button>
        <span v-if="form.file" class="file-meta">
          {{ (form.file.size / 1024 / 1024).toFixed(2) }} MB
        </span>
        <span class="field-hint" style="margin-left:6px">
          {{ clientType === 'pc' ? '支持 .zip / .exe' : '支持 .lrj / .apk' }}
        </span>
      </div>
    </el-form-item>

    <el-form-item>
      <el-button
        type="primary"
        :loading="uploading"
        @click="submitUpload"
        :disabled="!form.file"
      >
        {{ uploading ? '上传中...' : '发布新版本' }}
      </el-button>
    </el-form-item>

    <!-- 上传进度 -->
    <el-progress
      v-if="uploading"
      :percentage="uploadProgress"
      :stroke-width="6"
      style="margin-top:-8px"
    />
  </el-form>
</template>

<script setup>
import { ref, reactive } from 'vue'
import { Upload } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import { storage } from '@/utils/storage'

const props = defineProps({
  clientType: { type: String, required: true },  // 'pc' | 'android'
  projectId:  { type: Number, required: true },
})

const emit = defineEmits(['uploaded'])

const formRef      = ref(null)
const fileInput    = ref(null)
const uploading    = ref(false)
const uploadProgress = ref(0)

const form = reactive({
  version:       '',
  force_update:  false,
  release_notes: '',
  file:          null,
})

const rules = {
  version: [
    { required: true, message: '请输入版本号', trigger: 'blur' },
    { pattern: /^\d+\.\d+\.\d+$/, message: '格式：MAJOR.MINOR.PATCH（如 1.0.1）', trigger: 'blur' },
  ],
  file: [{ required: true, message: '请选择文件', trigger: 'change' }],
}

const onFileChange = (e) => {
  form.file = e.target.files[0] ?? null
}

const submitUpload = async () => {
  if (!await formRef.value?.validate().catch(() => false)) return
  if (!form.file) { ElMessage.warning('请选择文件'); return }

  uploading.value      = true
  uploadProgress.value = 0

  try {
    const fd = new FormData()
    fd.append('version',       form.version)
    fd.append('force_update',  form.force_update)
    fd.append('release_notes', form.release_notes ?? '')
    fd.append('file',          form.file)

    await axios.post(
      `/admin/api/updates/${props.projectId}/${props.clientType}`,
      fd,
      {
        headers: {
          'Content-Type':  'multipart/form-data',
          'Authorization': `Bearer ${storage.getToken()}`,
        },
        onUploadProgress: (evt) => {
          if (evt.total) {
            uploadProgress.value = Math.round(evt.loaded / evt.total * 100)
          }
        },
      }
    )

    ElMessage.success(`${props.clientType === 'pc' ? 'PC' : '安卓'} 端 v${form.version} 发布成功`)
    // 重置表单
    form.version       = ''
    form.force_update  = false
    form.release_notes = ''
    form.file          = null
    if (fileInput.value) fileInput.value.value = ''
    emit('uploaded')
  } catch (err) {
    const detail = err.response?.data?.detail
    ElMessage.error(typeof detail === 'string' ? detail : '上传失败，请重试')
  } finally {
    uploading.value      = false
    uploadProgress.value = 0
  }
}
</script>

<style scoped>
.upload-area { display: flex; align-items: center; gap: 10px; flex-wrap: wrap; }
.file-meta   { font-size: 12px; color: #475569; }
.field-hint  { font-size: 11px; color: #94a3b8; }
</style>
