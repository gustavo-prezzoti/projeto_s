import axios from 'axios';

const API_URL = 'http://localhost:8000';

const api = axios.create({
  baseURL: API_URL,
});

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
    const response = await api.get('/cnpj/consultar', { params: filters });
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

export default api; 