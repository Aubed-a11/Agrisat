import { useState } from 'react'
import { ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip } from 'recharts'
import { api, CROPS, fmt, pct } from '../api'
import { PageHeader, Section, Loading, useLoad } from '../components/ui'

const NAMES = { ridge: 'Régression pénalisée', random_forest: 'Forêt aléatoire', xgboost: 'XGBoost' }
const LABEL = (f) => {
  const m = { rain_cap: 'Pluie plafonnée', rain: 'Pluie totale', dry: 'Séquence sèche max', heavy: 'Jours de forte pluie', tmax: 'Température max', deficit: 'Bilan hydrique', ndvi_mean: 'NDVI moyen', ndvi_max: 'NDVI max', onset_doy: 'Démarrage de saison', sowing_doy: 'Date de semis' }
  const ph = f.match(/_p(\d)$/)
  const base = ph ? f.replace(/_p\d$/, '') : f
  return `${m[base] || base}${ph ? `, phase ${ph[1]}` : ''}`
}

export default function Models() {
  const [crop, setCrop] = useState('coton')
  const { data } = useLoad(() => api.get('/models'), [])
  if (!data) return <Loading />
  const r = data[crop]
  if (r?.skipped) return (
    <div>
      <PageHeader title="Modèles de rendement" actions={<select className="input w-32" value={crop} onChange={(e) => setCrop(e.target.value)}>{Object.entries(CROPS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>} />
      <Section><p className="text-sm text-ink/70">{r.skipped}. Le contrat de cette culture est conçu sur le seul climat et doit être validé dès que les rendements communaux sont disponibles.</p></Section>
    </div>)
  const top = r.shap.top_features.map((t) => ({ ...t, name: LABEL(t.feature) }))
  const phases = Object.entries(r.shap.by_phase).map(([k, v]) => ({ name: k, v }))
  return (
    <div>
      <PageHeader title="Modèles de rendement"
        description="Rendement relatif à la tendance expliqué par les indices satellitaires de chaque phase. Validation en excluant une année entière à chaque itération, car toutes les communes d'une même année partagent la même météo."
        actions={<select className="input w-32" value={crop} onChange={(e) => setCrop(e.target.value)}>{Object.entries(CROPS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}</select>} />
      <Section title={`Performance hors échantillon, ${r.n_obs} observations commune et année, ${r.n_years} campagnes`} className="mb-4">
        <table className="w-full">
          <thead><tr><th className="th">Modèle</th><th className="th num">R²</th><th className="th num">RMSE</th><th className="th num">MAE</th><th className="th num">AUC mauvaises années</th></tr></thead>
          <tbody>{Object.entries(r.metrics).map(([k, m]) => (
            <tr key={k} className={k === r.best_model ? 'bg-navy-50' : ''}><td className="td font-semibold">{NAMES[k]}{k === r.best_model ? ', retenu' : ''}</td>
              <td className="td num">{fmt(m.r2, 3)}</td><td className="td num">{pct(m.rmse)}</td><td className="td num">{pct(m.mae)}</td><td className="td num">{fmt(m.auc_bad_year, 3)}</td></tr>))}</tbody>
        </table>
        {r.metrics[r.best_model].r2 < 0.1 && <p className="text-sm text-alert-600 mb-2">Sur les rendements réels, les indices de pluie, de température et de NDVI n'expliquent pas les variations du rendement du maïs d'une année à l'autre : le R² hors échantillon est proche de zéro ou négatif. Dans le Nord Bénin, où il tombe environ 1 000 mm par an, le manque de pluie n'est pas le facteur dominant des pertes de maïs. L'indice pluie n'est donc pas commercialisé pour cette culture.</p>}
        <p className="text-xs text-ink/60 mt-3">Objectif du cahier des charges : R² supérieur à 0,5. L'AUC mesure la capacité à reconnaître les années de perte supérieure à 30 %. Erreurs exprimées en points de rendement relatif.</p>
      </Section>
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        <Section title={`Variables les plus déterminantes (${r.shap.method.toUpperCase()})`} className="lg:col-span-2">
          <div style={{ height: 420 }}>
            <ResponsiveContainer><BarChart data={top} layout="vertical" margin={{ left: 40 }}>
              <CartesianGrid stroke="#eee" horizontal={false} /><XAxis type="number" tick={{ fontSize: 11 }} /><YAxis type="category" dataKey="name" width={190} tick={{ fontSize: 11 }} />
              <Tooltip formatter={(v) => fmt(v, 4)} /><Bar dataKey="importance" fill="#1d4e89" name="Valeur SHAP moyenne absolue" />
            </BarChart></ResponsiveContainer>
          </div>
        </Section>
        <Section title="Poids de chaque phase">
          <div style={{ height: 260 }}>
            <ResponsiveContainer><BarChart data={phases}>
              <CartesianGrid stroke="#eee" vertical={false} /><XAxis dataKey="name" tick={{ fontSize: 11 }} /><YAxis tickFormatter={(v) => pct(v, 0)} tick={{ fontSize: 11 }} width={40} />
              <Tooltip formatter={(v) => pct(v, 1)} /><Bar dataKey="v" fill="#c4841d" name="Part de l'explication" />
            </BarChart></ResponsiveContainer>
          </div>
          <p className="text-xs text-ink/60 mt-2">Ces poids guident la répartition de la somme assurée entre les phases du contrat.</p>
        </Section>
      </div>
    </div>
  )
}
