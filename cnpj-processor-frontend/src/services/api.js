import axios from 'axios';
import { getToken } from './auth';

// Use relative path with /api prefix instead of absolute URL
// This allows it to work with proxy configurations
const api = axios.create({
  baseURL: '/api',
});

// Add a request interceptor to inject the auth token into every request
api.interceptors.request.use(
  (config) => {
    const token = getToken();
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error)
);

// Add a response interceptor to handle authentication errors
api.interceptors.response.use(
  (response) => response,
  (error) => {
    // Handle 401 Unauthorized errors
    if (error.response && error.response.status === 401) {
      // Redirect to login page
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

export const uploadExcel = async (file) => {
  const formData = new FormData();
  formData.append('file', file);
  
  try {
    const response = await api.post('/cnpj/process', formData);
    return response.data;
  } catch (error) {
    console.error('Erro ao fazer upload do arquivo', error);
    throw error;
  }
};

export const consultarCnpjs = async (filters = {}) => {
  try {
    const response = await api.get('/cnpj/list', { params: filters });
    return response.data;
  } catch (error) {
    console.error('Erro ao consultar CNPJs', error);
    throw error;
  }
};

export const reprocessarErros = async (textoErro = null, dias = null, limite = null) => {
  try {
    const params = {};
    if (textoErro) params.texto_erro = textoErro;
    if (dias !== null) params.dias = dias;
    if (limite) params.limite = limite;
    
    const response = await api.get('/cnpj/reprocessar-erros-recriando', { params });
    return response.data;
  } catch (error) {
    console.error('Erro ao reprocessar CNPJs com erro', error);
    throw error;
  }
};

export const reprocessarCnpjIndividual = async (cnpj_id, deletar_registro = true) => {
  try {
    // The API expects these parameters as query params
    const params = {
      cnpj_id,
      deletar_registro
    };
    
    const response = await api.get('/cnpj/reprocessar-cnpj-individual', { params });
    return response.data;
  } catch (error) {
    console.error('Erro ao reprocessar CNPJ individual', error);
    throw error;
  }
};

export const deletarCnpj = async (id) => {
  try {
    const response = await api.delete(`/cnpj/${id}`);
    // Retorna true se a deleção foi bem-sucedida (status 204)
    return response.status === 204;
  } catch (error) {
    console.error('Erro ao deletar CNPJ', error);
    throw error;
  }
};

export const deletarCnpjsEmLote = async (ids) => {
  try {
    const response = await api.delete('/cnpj/delete-batch', {
      data: { fila_ids: ids }
    });
    
    // Return full response object
    return response;
  } catch (error) {
    console.error('Erro ao deletar CNPJs em lote', error);
    throw error;
  }
};

export default api; 