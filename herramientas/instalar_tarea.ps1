# Programa herramientas/actualizar_desde_pc.py en Windows: 11:30 y 19:00.
# El OECE publica su lote diario hacia las 10:30; 19:00 recoge lo que llegue tarde.
# Si la PC está apagada a esa hora, corre apenas se encienda.
# Uso (PowerShell, sin permisos de administrador):
#   powershell -ExecutionPolicy Bypass -File herramientas\instalar_tarea.ps1
# Para quitarla: Unregister-ScheduledTask -TaskName "Licitar Hoy - actualizar" -Confirm:$false

$repo = Split-Path -Parent $PSScriptRoot
$pythonw = Join-Path $repo ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonw)) { throw "No encuentro $pythonw (crea el .venv primero)" }

$accion = New-ScheduledTaskAction -Execute $pythonw `
  -Argument "herramientas\actualizar_desde_pc.py --log" -WorkingDirectory $repo
$disparadores = @(
  New-ScheduledTaskTrigger -Daily -At "11:30"
  New-ScheduledTaskTrigger -Daily -At "19:00"
)
$ajustes = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries `
  -DontStopIfGoingOnBatteries -ExecutionTimeLimit (New-TimeSpan -Hours 1) `
  -MultipleInstances IgnoreNew

Register-ScheduledTask -TaskName "Licitar Hoy - actualizar" -Action $accion `
  -Trigger $disparadores -Settings $ajustes -Force `
  -Description "Descarga licitaciones del OECE desde esta PC y publica licitarhoy.toca.pe. Log: out\pc\actualizar.log" | Out-Null

Write-Host "Tarea instalada: 11:30 y 19:00. Log en $repo\out\pc\actualizar.log"
