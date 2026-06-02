# qm.ps1 — QuickMind CLI rapide via PowerShell
# Usage :
#   .\qm.ps1 "Titre de la tache"
#   .\qm.ps1 "Titre" -p urgent -c Travail
#   .\qm.ps1 "Titre" -r "25/05/2026 09:00"
#   .\qm.ps1 list
#   .\qm.ps1 done 5
#   .\qm.ps1 ai "Preparer la demo vendredi 14h"
#   .\qm.ps1 health

param(
    [Parameter(Position=0)] [string] $Command = "",
    [Parameter(Position=1)] [string] $Arg2    = "",
    [string] $p = "normal",
    [string] $c = "",
    [string] $r = "",
    [string] $d = ""
)

$API = "http://localhost:8765"

function Show-Help {
    Write-Host ""
    Write-Host "  QuickMind - CLI PowerShell" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "  Usage :" -ForegroundColor Yellow
    Write-Host '  .\qm.ps1 "Titre"                         Creer une tache'
    Write-Host '  .\qm.ps1 "Titre" -p urgent -c Travail    Priorite + categorie'
    Write-Host '  .\qm.ps1 "Titre" -r "25/05/2026 09:00"   Avec rappel'
    Write-Host '  .\qm.ps1 list                             Lister les taches'
    Write-Host '  .\qm.ps1 list -p urgent                   Lister les urgentes'
    Write-Host '  .\qm.ps1 done 5                           Marquer tache #5 terminee'
    Write-Host '  .\qm.ps1 ai "texte libre"                 Creer via IA (Mistral)'
    Write-Host '  .\qm.ps1 health                           Verifier QuickMind'
    Write-Host ""
}

function Test-QuickMind {
    try {
        $res = Invoke-RestMethod -Uri "$API/health" -Method GET -TimeoutSec 3
        return $res
    } catch {
        return $null
    }
}

# ── HEALTH ────────────────────────────────────────────────────────────────────
if ($Command -eq "health") {
    $h = Test-QuickMind
    if ($h) {
        Write-Host "OK QuickMind actif - $($h.tasks) tache(s)" -ForegroundColor Green
    } else {
        Write-Host "ERREUR QuickMind ne repond pas sur $API" -ForegroundColor Red
        Write-Host "Lance QuickMind puis reessaie." -ForegroundColor Yellow
    }
    exit
}

# ── AIDE ──────────────────────────────────────────────────────────────────────
if ($Command -eq "" -or $Command -eq "help") {
    $h = Test-QuickMind
    if ($h) {
        Write-Host "OK QuickMind actif - $($h.tasks) tache(s)" -ForegroundColor Green
    } else {
        Write-Host "ATTENTION QuickMind hors ligne" -ForegroundColor Yellow
    }
    Show-Help
    exit
}

# ── LIST ──────────────────────────────────────────────────────────────────────
if ($Command -eq "list" -or $Command -eq "ls") {
    try {
        $url = "$API/tasks"
        $params_list = @{}
        if ($p -ne "normal" -and $p -ne "") { $params_list["priority"] = $p }
        if ($c -ne "") { $params_list["category"] = $c }

        $uri = $url
        if ($params_list.Count -gt 0) {
            $qs = ($params_list.GetEnumerator() | ForEach-Object { "$($_.Key)=$($_.Value)" }) -join "&"
            $uri = "$url?$qs"
        }

        $tasks = Invoke-RestMethod -Uri $uri -Method GET
        if ($tasks.Count -eq 0) {
            Write-Host "Aucune tache trouvee." -ForegroundColor Gray
        } else {
            Write-Host ""
            Write-Host ("  {0,-4} {1,-32} {2,-8} {3,-12} {4}" -f "ID","Titre","Priorite","Statut","Categorie") -ForegroundColor Cyan
            Write-Host ("  {0,-4} {1,-32} {2,-8} {3,-12} {4}" -f "----","--------------------------------","--------","------------","----------") -ForegroundColor DarkGray
            foreach ($t in $tasks) {
                $pcolor = "White"
                if ($t.priority -eq "urgent") { $pcolor = "Red" }
                elseif ($t.priority -eq "high") { $pcolor = "Yellow" }
                elseif ($t.priority -eq "low")  { $pcolor = "DarkGray" }
                $titleShort = if ($t.title.Length -gt 30) { $t.title.Substring(0,30) + "..." } else { $t.title }
                Write-Host ("  {0,-4} {1,-32} {2,-8} {3,-12} {4}" -f "#$($t.id)", $titleShort, $t.priority, $t.status, $t.category) -ForegroundColor $pcolor
            }
            Write-Host ""
            Write-Host "  $($tasks.Count) tache(s)" -ForegroundColor Gray
        }
    } catch {
        Write-Host "ERREUR $_" -ForegroundColor Red
    }
    exit
}

# ── DONE ──────────────────────────────────────────────────────────────────────
if ($Command -eq "done") {
    if ($Arg2 -eq "") {
        Write-Host "Usage : .\qm.ps1 done <ID>" -ForegroundColor Yellow
        exit
    }
    try {
        Invoke-RestMethod -Uri "$API/task/$Arg2/done" -Method POST | Out-Null
        Write-Host "OK Tache #$Arg2 marquee comme terminee." -ForegroundColor Green
    } catch {
        Write-Host "ERREUR $_" -ForegroundColor Red
    }
    exit
}

# ── AI ────────────────────────────────────────────────────────────────────────
if ($Command -eq "ai") {
    if ($Arg2 -eq "") {
        Write-Host "Usage : .\qm.ps1 ai `"texte libre`"" -ForegroundColor Yellow
        exit
    }
    try {
        Write-Host "Mistral analyse..." -ForegroundColor Cyan
        $bodyObj = @{ text = $Arg2 }
        $bodyJson = $bodyObj | ConvertTo-Json -Compress
        $res = Invoke-RestMethod -Uri "$API/task/ai" -Method POST -Body $bodyJson -ContentType "application/json"
        Write-Host "OK $($res.result)" -ForegroundColor Green
    } catch {
        Write-Host "ERREUR $_" -ForegroundColor Red
    }
    exit
}

# ── DELETE ────────────────────────────────────────────────────────────────────
if ($Command -eq "delete" -or $Command -eq "rm") {
    if ($Arg2 -eq "") {
        Write-Host "Usage : .\qm.ps1 delete <ID>" -ForegroundColor Yellow
        exit
    }
    try {
        Invoke-RestMethod -Uri "$API/task/$Arg2" -Method DELETE | Out-Null
        Write-Host "OK Tache #$Arg2 supprimee." -ForegroundColor Green
    } catch {
        Write-Host "ERREUR $_" -ForegroundColor Red
    }
    exit
}

# ── CREER TACHE (defaut) ──────────────────────────────────────────────────────
try {
    $bodyObj = @{
        title       = $Command
        description = $d
        category    = $c
        priority    = $p
    }
    if ($r -ne "") { $bodyObj["reminder"] = $r }

    $bodyJson = $bodyObj | ConvertTo-Json -Compress
    $res = Invoke-RestMethod -Uri "$API/task" -Method POST -Body $bodyJson -ContentType "application/json"
    Write-Host "OK Tache #$($res.id) creee : $($res.title)" -ForegroundColor Green
} catch {
    Write-Host "ERREUR $_" -ForegroundColor Red
    Write-Host "QuickMind tourne-t-il ? Lance : .\qm.ps1 health" -ForegroundColor Yellow
}
