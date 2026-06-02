# outlook_rule.ps1
# Configure une regle Outlook pour creer des taches QuickMind automatiquement.
# Usage : .\outlook_rule.ps1
# Format mail : QUICKMIND: Titre [priorite] [Categorie]

$API        = "http://localhost:8765"
$ScriptPath = "$env:USERPROFILE\QuickMind_MailRule.ps1"

Write-Host ""
Write-Host "  QuickMind - Configuration regle Outlook" -ForegroundColor Cyan
Write-Host ""

# 1. Verifier que QuickMind tourne
try {
    $health = Invoke-RestMethod -Uri "$API/health" -Method GET -TimeoutSec 3
    Write-Host "  OK QuickMind actif ($($health.tasks) taches)" -ForegroundColor Green
} catch {
    Write-Host "  ERREUR QuickMind ne repond pas." -ForegroundColor Red
    Write-Host "  Lance QuickMind d abord puis reessaie." -ForegroundColor Yellow
    exit 1
}

Write-Host ""
Write-Host "  Regle qui sera creee :" -ForegroundColor Yellow
Write-Host "    - Sujet contient : QUICKMIND:"
Write-Host "    - Action : creation automatique d une tache"
Write-Host ""
Write-Host "  Format sujet :"
Write-Host "    QUICKMIND: Titre de la tache"
Write-Host "    QUICKMIND: Titre [urgent] [Travail]"
Write-Host "    QUICKMIND: Titre [high] [Projets]"
Write-Host ""

# 2. Creer le script de traitement des mails
$lines = @()
$lines += "# QuickMind_MailRule.ps1 - Execute par la regle Outlook"
$lines += "param([string]`$Subject, [string]`$Body, [string]`$Sender)"
$lines += ""
$lines += "`$API = `"http://localhost:8765`""
$lines += ""
$lines += "# Extraire le titre"
$lines += "`$title = `$Subject -replace `"^QUICKMIND:\s*`", `"`""
$lines += "`$title = `$title -replace `"\s*\[.*?\]\s*`", `"`""
$lines += "`$title = `$title.Trim()"
$lines += ""
$lines += "# Extraire la priorite"
$lines += "`$priority = `"normal`""
$lines += "if (`$Subject -match `"\[urgent\]`") { `$priority = `"urgent`" }"
$lines += "elseif (`$Subject -match `"\[high\]`") { `$priority = `"high`" }"
$lines += "elseif (`$Subject -match `"\[low\]`") { `$priority = `"low`" }"
$lines += ""
$lines += "# Extraire la categorie"
$lines += "`$category = `"`""
$lines += "`$reserved = @(`"urgent`", `"high`", `"low`", `"normal`")"
$lines += "if (`$Subject -match `"\[([A-Za-z\s/]+)\]`") {"
$lines += "    `$cat = `$Matches[1].Trim()"
$lines += "    if (`$reserved -notcontains `$cat.ToLower()) {"
$lines += "        `$category = `$cat"
$lines += "    }"
$lines += "}"
$lines += ""
$lines += "# Description depuis le corps du mail"
$lines += "`$maxLen = [Math]::Min(500, `$Body.Length)"
$lines += "`$desc = `"De : `$Sender`n`n`" + `$Body.Substring(0, `$maxLen)"
$lines += ""
$lines += "# Construire le JSON"
$lines += "`$obj = @{"
$lines += "    title       = `$title"
$lines += "    description = `$desc"
$lines += "    priority    = `$priority"
$lines += "    category    = `$category"
$lines += "}"
$lines += "`$json = `$obj | ConvertTo-Json -Compress"
$lines += ""
$lines += "# Envoyer a QuickMind"
$lines += "try {"
$lines += "    Invoke-RestMethod -Uri `"`$API/task`" -Method POST -Body `$json -ContentType `"application/json`" | Out-Null"
$lines += "} catch {"
$lines += "    # Silencieux si QuickMind ne tourne pas"
$lines += "}"

$lines | Out-File -FilePath $ScriptPath -Encoding UTF8
Write-Host "  OK Script cree : $ScriptPath" -ForegroundColor Green

# 3. Creer la regle Outlook via COM
try {
    $outlook = New-Object -ComObject Outlook.Application
    $rules   = $outlook.Session.DefaultStore.GetRules()

    # Supprimer si existe deja
    for ($i = 1; $i -le $rules.Count; $i++) {
        if ($rules.Item($i).Name -eq "QuickMind") {
            $rules.Remove("QuickMind")
            Write-Host "  Ancienne regle supprimee." -ForegroundColor Yellow
            break
        }
    }

    # Creer la nouvelle regle
    $rule = $rules.Create("QuickMind", 0)

    # Condition : sujet contient QUICKMIND:
    $cond = $rule.Conditions.Subject
    $cond.Enabled = $true
    $cond.Text    = @("QUICKMIND:")

    # Action : executer script
    $action = $rule.Actions.RunScript
    $action.Enabled    = $true
    $action.ScriptName = $ScriptPath

    $rule.Enabled = $true
    $rules.Save()

    Write-Host "  OK Regle Outlook QuickMind creee !" -ForegroundColor Green
    Write-Host ""
    Write-Host "  Test : envoie-toi un mail avec le sujet :" -ForegroundColor Cyan
    Write-Host "    QUICKMIND: Ma premiere tache [urgent] [Travail]" -ForegroundColor White
    Write-Host ""

} catch {
    Write-Host ""
    Write-Host "  ERREUR creation regle Outlook : $_" -ForegroundColor Red
    Write-Host ""
    Write-Host "  Solution manuelle dans Outlook :" -ForegroundColor Yellow
    Write-Host "    1. Fichier -> Gerer les regles et alertes"
    Write-Host "    2. Nouvelle regle -> A la reception"
    Write-Host "    3. Condition : le sujet contient QUICKMIND:"
    Write-Host "    4. Action    : executer un script"
    Write-Host "    5. Script    : $ScriptPath"
    Write-Host ""
}
