// Spec-Refs: GOV-SPEC-001, GOV-SPEC-004, GOV-SPEC-006.
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { expect, it, vi } from 'vitest'
import { ObservedScanTimes } from './DesktopTimeline'
const times=['2026-09-09T01:40:21Z','2026-09-09T01:50:21Z']
const row={id:'noaa-goes19-demand-cloud-mask',title:'GOES-19 observed cloud mask',inventory:{frames:times.map(valid_time=>({valid_time,run_time:valid_time})),notices:[],expires_at:'2026-09-09T02:03:00Z'}}
it('exposes actual timestamps while the selected time is in the future, without auto-selection',async()=>{
  const onPick=vi.fn(),user=userEvent.setup()
  const {rerender}=render(<ObservedScanTimes row={row} selectedMs={Date.parse('2026-09-09T22:00:00Z')} onPick={onPick} />)
  const select=screen.getByRole('combobox',{name:'GOES-19 available scan timestamps'})
  expect(select).toHaveValue('')
  expect(screen.getByRole('option',{name:/2026-09-09 01:40:21 UTC/})).toBeInTheDocument()
  expect(onPick).not.toHaveBeenCalled()
  await user.selectOptions(select,times[0]);expect(onPick).toHaveBeenLastCalledWith(Date.parse(times[0]))
  await user.click(screen.getByRole('button',{name:'Latest GOES scan'}));expect(onPick).toHaveBeenLastCalledWith(Date.parse(times[1]))
  rerender(<ObservedScanTimes row={row} selectedMs={Date.parse(times[1])} onPick={onPick} />)
  expect(select).toHaveValue(times[1])
})
it('discloses unavailable inventory without offering invented timestamps',()=>{
  render(<ObservedScanTimes row={{id:row.id,title:row.title,error:'Inventory unavailable'}} selectedMs={0} onPick={vi.fn()} />)
  expect(screen.getByRole('combobox')).toBeDisabled()
  expect(screen.queryByRole('button',{name:'Latest GOES scan'})).not.toBeInTheDocument()
})
