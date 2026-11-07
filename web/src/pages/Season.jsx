import { useEffect, useMemo, useState } from 'react'
import { MapContainer, TileLayer, GeoJSON, Tooltip, CircleMarker } from 'react-leaflet'
import { ResponsiveContainer, ComposedChart, Line, Area, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip, Legend } from 'recharts'
import { api, CROPS, dateLabel, isoDate, fmt, pct } from '../api'
import { useMeta } from '../main'
import { PageHeader, Status, STATUS_COLOR, Section, Loading, ErrorBox, Stat } from '../components/ui'

export default function Season() {
  const meta = useMeta()
  const year = meta?.campaign
  const [crop, setCrop] = useState('coton')
  const [doy, setDoy] = useState(236)
  const [debounced, setDebounced] = useState(236)
  const [rows, setRows] = useState(null)
  const [sel, setSel] = useState(1)
  const [detail, setDetail] = useState(null)
  const [err, setErr] = useState(null)
  const [geo, setGeo] = useState(null)
  useEffect(() => { api.get('/geo/communes').then(setGeo).catch(() => setGeo(false)) }, [])

  useEffect(() => { const t = setTimeout(() => setDebounced(doy), 250); return () => clearTimeout(t) }, [doy])
  useEffect(() => {
    if (!year) return
    api.get(`/season?crop=${crop}&year=${year}&asof=${isoDate(year, debounced)}`).then(setRows).catch((e) => setErr(e.message))
  }, [crop, debounced, year])
  useEffect(() => {
    if (!year) return
    api.get(`/season/${sel}?crop=${crop}&year=${year}&asof=${isoDate(year, debounced)}`).then(setDetail).catch((e) => setErr(e.message))
  }, [sel, crop, debounced, year])

  const counts = useMemo(() => (rows || []).reduce((a, r) => ({ ...a, [r.status]: (a[r.status] || 0) + 1 }), {}), [rows])
  if (!meta) return <Loading />
  const series = detail?.series?.filter((p) => p.doy >= 100 && p.doy <= 340).map((p) => ({ ...p, date: dateLabel(year, p.doy) }))

  return (
    <div>
      <PageHeader title={`Suivi de la saison ${year}`}
        description="État des indices de pluie par commune à la date choisie. Une phase terminée sous le seuil déclenche l'assurance, une phase en cours dont la projection reste proche du seuil passe en vigilance."
        actions={<>
          <select className="input w-36" value={crop} onChange={(e) => setCrop(e.target.value)}>
            {Object.entries(CROPS).map(([k, v]) => <option key={k} value={k}>{v}</option>)}
          </select>
        </>} />
      <ErrorBox error={err} />
      <div className="card p-4 mb-4">
        <div className="flex items-center justify-between text-sm mb-2">
          <span className="font-semibold">Données disponibles au {dateLabel(year, doy)} {year}</span>
          <span className="text-ink/60">Mise à jour par décade, pluie CHIRPS et NDVI MODIS</span>
        </div>
        <input type="range" min={120} max={334} step={1} value={doy} onChange={(e) => setDoy(+e.target.value)} className="w-full accent-navy-700" />
        <div className="flex justify-between text-xs text-ink/50 mt-1">{['1 mai', '1 juin', '1 juil.', '1 août', '1 sept.', '1 oct.', '1 nov.', '30 nov.'].map((m) => <span key={m}>{m}</span>)}</div>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-4">
        <Stat label="Communes en situation normale" value={counts.normal || 0} />
        <Stat label="Communes en vigilance" value={counts.vigilance || 0} tone="ochre" />
        <Stat label="Communes déclenchées" value={counts.declenche || 0} tone="alert" />
        <Stat label="Communes avant semis" value={counts.hors_saison || 0} />
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-4">
        <div className="lg:col-span-2 card overflow-hidden h-[380px] lg:h-[560px]">
          <MapContainer center={[10.4, 2.2]} zoom={7} style={{ height: '100%' }} scrollWheelZoom={false}>
            <TileLayer attribution='&copy; OpenStreetMap' url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png" />
            {geo && rows && (
              <GeoJSON key={`${debounced}-${crop}-${sel}`} data={geo}
                style={(f) => {
                  const r = rows.find((x) => x.commune_id === f.properties.commune_id)
                  const active = sel === f.properties.commune_id
                  return { color: active ? '#0b2545' : '#ffffff', weight: active ? 2.5 : 1, fillColor: STATUS_COLOR[r?.status] || '#c7d3df', fillOpacity: 0.85 }
                }}
                onEachFeature={(f, layer) => {
                  const r = rows.find((x) => x.commune_id === f.properties.commune_id)
                  layer.on('click', () => setSel(f.properties.commune_id))
                  if (r) layer.bindTooltip(`<b>${r.commune}</b><br/>Pluie ${fmt(r.rain_to_date)} mm, normale ${fmt(r.rain_normal_to_date)} mm`, { sticky: true })
                }} />
            )}
            {geo === false && (rows || []).map((r) => (
              <CircleMarker key={r.commune_id} center={[r.lat, r.lon]} radius={10}
                pathOptions={{ color: '#fff', weight: 2, fillColor: STATUS_COLOR[r.status], fillOpacity: 0.9 }}
                eventHandlers={{ click: () => setSel(r.commune_id) }}>
                <Tooltip><b>{r.commune}</b></Tooltip>
              </CircleMarker>
            ))}
          </MapContainer>
        </div>
        <div className="lg:col-span-3 space-y-4">
          {detail && (
            <Section title={`${detail.commune}, ${detail.department}`} actions={<Status value={detail.status} />}>
              <div className="grid grid-cols-3 gap-3 text-sm mb-4">
                <div><div className="text-ink/60 text-xs">Démarrage de la saison</div><div className="font-semibold">{dateLabel(year, detail.onset_doy)} {detail.onset_confirmed ? '' : '(provisoire)'}</div></div>
                <div><div className="text-ink/60 text-xs">Semis retenu</div><div className="font-semibold">{dateLabel(year, detail.sowing_doy)}</div></div>
                <div><div className="text-ink/60 text-xs">Pluie cumulée et normale</div><div className="font-semibold">{fmt(detail.rain_to_date)} mm sur {fmt(detail.rain_normal_to_date)} mm</div></div>
              </div>
              <div className="text-xs font-semibold text-ink/60 mb-1">Pluie cumulée depuis le 1er janvier (mm)</div>
              <div style={{ height: 210 }}>
                <ResponsiveContainer>
                  <ComposedChart data={series} margin={{ left: 0, right: 8, top: 4 }}>
                    <CartesianGrid stroke="#eee" vertical={false} />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} interval={5} />
                    <YAxis tick={{ fontSize: 11 }} width={44} />
                    <RTooltip formatter={(v) => `${fmt(v)} mm`} />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                    <Area dataKey="normal_cum" name="Normale 1981 à 2025" stroke="#9fb3c8" fill="#d6e6f3" fillOpacity={0.5} />
                    <Line dataKey="dry_year_cum" name="Année sèche (2 ans sur 10)" stroke="#c4841d" strokeDasharray="4 3" dot={false} />
                    <Line dataKey="rain_cum" name={`${year}`} stroke="#0b2545" strokeWidth={2.2} dot={false} connectNulls={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
              <div className="text-xs font-semibold text-ink/60 mb-1 mt-3">NDVI, vigueur de la végétation</div>
              <div style={{ height: 150 }}>
                <ResponsiveContainer>
                  <ComposedChart data={series} margin={{ left: 0, right: 8, top: 4 }}>
                    <CartesianGrid stroke="#eee" vertical={false} />
                    <XAxis dataKey="date" tick={{ fontSize: 11 }} interval={5} />
                    <YAxis domain={[0.15, 0.8]} tick={{ fontSize: 11 }} width={44} />
                    <RTooltip formatter={(v) => fmt(v, 2)} />
                    <Line dataKey="ndvi_normal" name="Moyenne" stroke="#9fb3c8" dot={false} />
                    <Line dataKey="ndvi" name={`${year}`} stroke="#3d8cc0" strokeWidth={2} dot={false} />
                  </ComposedChart>
                </ResponsiveContainer>
              </div>
            </Section>
          )}
          {detail && (
            <Section title="Phases du contrat">
              <div className="overflow-x-auto"><table className="w-full">
                <thead><tr><th className="th">Phase</th><th className="th">Période</th><th className="th">État</th><th className="th num">Pluie observée</th><th className="th num">Projection</th><th className="th num">Seuil</th><th className="th num">Sortie</th><th className="th num">Indemnité</th></tr></thead>
                <tbody>
                  {detail.phases.map((p) => (
                    <tr key={p.phase} className={p.weight === 0 ? 'text-ink/40' : ''}>
                      <td className="td">{p.phase}. {p.name}</td>
                      <td className="td whitespace-nowrap">{dateLabel(year, p.start_doy)} au {dateLabel(year, p.end_doy - 1)}</td>
                      <td className="td"><Status value={p.status} /></td>
                      <td className="td num">{fmt(p.index_observed)} mm</td>
                      <td className="td num">{p.status === 'terminee' ? '' : `${fmt(p.index_projected)} mm`}</td>
                      <td className="td num">{p.weight ? `${fmt(p.trigger)} mm` : 'non couverte'}</td>
                      <td className="td num">{p.weight ? `${fmt(p.exit)} mm` : ''}</td>
                      <td className="td num font-semibold">{p.payout_fraction ? pct(p.payout_fraction) : ''}</td>
                    </tr>
                  ))}
                </tbody>
              </table></div>
              <p className="text-xs text-ink/55 mt-3">Indemnité exprimée en part de la somme assurée. Pluie journalière plafonnée à 50 mm dans l'indice. La phase de maturation du coton, en saison sèche, relève de la garantie excès de pluie.</p>
            </Section>
          )}
        </div>
      </div>
      <Section title="Toutes les communes" className="mt-4">
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead><tr><th className="th">Commune</th><th className="th">Département</th><th className="th">État</th><th className="th num">Pluie cumulée</th><th className="th num">Normale</th><th className="th num">Écart</th><th className="th num">Indemnité acquise</th></tr></thead>
            <tbody>
              {(rows || []).map((r) => (
                <tr key={r.commune_id} onClick={() => setSel(r.commune_id)} className={`cursor-pointer hover:bg-mist-50 ${sel === r.commune_id ? 'bg-navy-50' : ''}`}>
                  <td className="td font-semibold">{r.commune}</td><td className="td">{r.department}</td><td className="td"><Status value={r.status} /></td>
                  <td className="td num">{fmt(r.rain_to_date)} mm</td><td className="td num">{fmt(r.rain_normal_to_date)} mm</td>
                  <td className={`td num ${r.rain_to_date < r.rain_normal_to_date * 0.8 ? 'text-alert-600 font-semibold' : ''}`}>{pct(r.rain_to_date / r.rain_normal_to_date - 1, 0)}</td>
                  <td className="td num">{r.payout_fraction_to_date ? pct(r.payout_fraction_to_date) : ''}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </div>
  )
}
