"""Diagnostic estimates only. Never injects values into MS3 fueling inputs."""
def temperature_estimates(thermal,*,mat_placement_verified=False,ambient_placement_verified=False):
    def estimate(keys,quality):
        readings=[thermal.get(key) for key in keys] if thermal.online else []
        valid=[r for r in readings if r is not None and r.valid]
        if not valid:return dict(value_c=None,quality='INVALID',sources=[])
        return dict(value_c=max(r.temperature_c for r in valid),quality=quality,sources=[r.key for r in valid])
    coolant=estimate(('HEAD_COOLANT_LEFT','HEAD_COOLANT_RIGHT'),'DEGRADED')
    if len(coolant['sources'])==2:coolant['quality']='VALID'
    mat=estimate(('PLENUM_IAT',),'VALID')
    if mat['quality']=='INVALID' and mat_placement_verified:
        mat=estimate(('POST_WMI','IC_OUT_LEFT','IC_OUT_RIGHT','RUNNER_IAT_LEFT','RUNNER_IAT_RIGHT'),'ESTIMATED')
    ambient=estimate(('AMBIENT_AIR',),'VALID')
    if ambient['quality']=='INVALID' and ambient_placement_verified:
        ambient=estimate(('COMP_IN_LEFT','COMP_IN_RIGHT'),'ESTIMATED')
    return dict(coolant=coolant,mat=mat,ambient=ambient,ecu_substitution_enabled=False)
