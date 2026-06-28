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
  useEffect(()=>{
    fetch(`${API}/api/categories`).then(r=>r.json()).then(setCategories).catch(()=>setCategories([]));
  },[]);
  useEffect(()=>{
    const params=new URLSearchParams({q, category, limit:'80'});
    fetch(`${API}/api/products?${params}`)
      .then(r=>r.json())
      .then(data=>{ setProducts(data.items||[]); setTotal(data.total||0); })
      .catch(()=>{ setProducts([]); setTotal(0); });
  },[q,category]);
  async function upload(e){
    const f=e.target.files?.[0]; if(!f) return;
    const fd=new FormData(); fd.append('file',f);
    const res=await fetch(`${API}/api/match`,{method:'POST',body:fd});
    setMatches(await res.json());
  }
  return <main>
    <header><h1>Hahishook Switcher</h1><p>Search the cheap catalog and map baskets from expensive grocery sites.</p></header>
    <section className="panel">
      <label className="search"><Search size={18}/><input value={q} onChange={e=>setQ(e.target.value)} placeholder="Search products or category, Hebrew works" /></label>
      <select value={category} onChange={e=>setCategory(e.target.value)}>
        <option value="">All categories ({categories.reduce((s,c)=>s+c.count,0)})</option>
        {categories.map((c,i)=><option key={i} value={c.category}>{c.category} ({c.count})</option>)}
      </select>
      <small>{total} results</small>
      <div className="grid">{products.map((p,i)=><article key={i} className="card">
        {p.image_url && <img src={p.image_url}/>}<h3>{p.name}</h3><p>{p.size_text || ''}</p><b>{p.price_nis ? `₪${p.price_nis}` : 'No price'}</b><small>{p.unit_price_text || p.category || ''}</small>{p.product_url && <a href={p.product_url} target="_blank">Open product</a>}
      </article>)}</div>
    </section>
    <section className="panel">
      <h2>Basket matcher</h2><p>Upload CSV/XLSX. First column can be the product name, or use a column named name/product/item/שם/מוצר.</p>
      <label className="upload"><Upload size={18}/> Upload basket <input type="file" accept=".csv,.xlsx,.xls" onChange={upload}/></label>
      {matches.length>0 && <table><thead><tr><th>Input</th><th>Match</th><th>Score</th><th>Price</th><th>Size</th></tr></thead><tbody>{matches.map((m,i)=><tr key={i}><td>{m.input_name}</td><td>{m.matched_name}</td><td>{m.score}</td><td>{m.hahishook_price_nis}</td><td>{m.size_text}</td></tr>)}</tbody></table>}
    </section>
  </main>
}

createRoot(document.getElementById('root')).render(<App/>);
