import React, {useEffect, useState} from 'react';
import {createRoot} from 'react-dom/client';
import {Search, Upload} from 'lucide-react';
import './style.css';

const API = import.meta.env.VITE_API_URL || 'http://localhost:8000';

function App(){
  const [q,setQ]=useState('');
  const [category,setCategory]=useState('');
  const [categories,setCategories]=useState([]);
  const [products,setProducts]=useState([]);
  const [total,setTotal]=useState(0);
  const [matches,setMatches]=useState([]);
  const [searchError, setSearchError] = useState('');
  const [uploadStatus, setUploadStatus] = useState('');
  const [uploading, setUploading] = useState(false);
  useEffect(()=>{
    fetch(`${API}/api/categories`).then(r=>r.json()).then(setCategories).catch(()=>setCategories([]));
  },[]);
  useEffect(()=>{
    const controller = new AbortController();
    const params=new URLSearchParams({q, category, limit:'80'});
    fetch(`${API}/api/products?${params}`, {signal: controller.signal})
      .then(r => {
        if (!r.ok) throw new Error('Catalog request failed');
        return r.json();
      })
      .then(data => { setProducts(data.items); setTotal(data.total); setSearchError(''); })
      .catch(error => {
        if (error.name === 'AbortError') return;
        setProducts([]);
        setTotal(0);
        setSearchError('Could not reach the catalog API. Check that it is running.');
      });
    return () => controller.abort();
  },[q,category]);
  async function upload(e){
    const input = e.target;
    const file = input.files?.[0];
    if (!file) return;
    input.value = '';
    setMatches([]);
    setUploading(true);
    setUploadStatus('Matching products…');
    try {
      const body = new FormData();
      body.append('file', file);
      const response = await fetch(`${API}/api/match`, {method: 'POST', body});
      const result = await response.json();
      if (!response.ok) {
        setUploadStatus(typeof result.detail === 'string' ? result.detail : 'Could not match this basket.');
        return;
      }
      setMatches(result);
      setUploadStatus('');
    } catch {
      setUploadStatus('Could not reach the basket matcher. Try again.');
    } finally {
      setUploading(false);
    }
  }
  return <main>
    <header><h1>Hahishook Switcher</h1><p>Search the cheap catalog and map baskets from expensive grocery sites.</p></header>
    <section className="panel">
      <label className="search"><Search size={18}/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search products or category, Hebrew works" /></label>
      <select value={category} onChange={e=>setCategory(e.target.value)}>
        <option value="">All categories ({categories.reduce((s,c)=>s+c.count,0)})</option>
        {categories.map((c,i)=><option key={i} value={c.category}>{c.category} ({c.count})</option>)}
      </select>
      <small role="status">{searchError || `${total} results`}</small>
      <div className="grid">{products.map((p,i)=><article key={i} className="card">
        {p.image_url && <img src={p.image_url}/>}<h3>{p.name}</h3><p>{p.size_text || ''}</p><b>{p.price_nis ? `₪${p.price_nis}` : 'No price'}</b><small>{p.unit_price_text || p.category || ''}</small>{p.product_url && <a href={p.product_url} target="_blank">Open product</a>}
      </article>)}</div>
    </section>
    <section className="panel">
      <h2>Basket matcher</h2><p>Upload CSV/XLSX. First column can be the product name, or use a column named name/product/item/שם/מוצר.</p>
      <label className="upload"><Upload size={18}/> Upload basket <input type="file" accept=".csv,.xlsx,.xls" onChange={upload} disabled={uploading}/></label>
      <p role="status">{uploadStatus}</p>
      {matches.length>0 && <div className="basket-results"><table><thead><tr><th>Input</th><th>Match</th><th>Store</th><th>Score</th><th>Price</th><th>Size</th></tr></thead><tbody>{matches.map((m,i)=><tr key={i}><td>{m.input_name}</td><td>{m.matched_name || 'No match'}</td><td>{m.matched_source}</td><td>{m.score}</td><td>{m.hahishook_price_nis}</td><td>{m.size_text}</td></tr>)}</tbody></table></div>}
    </section>
  </main>
}

createRoot(document.getElementById('root')).render(<App/>);
