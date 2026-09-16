$pptx = "e:\yuvi_workspace\WORKSPACE\antigravity_workspace\ai-poc\output\Introduction_and_analysis_of_GPT_6_Astra_its_capabilities_pe.pptx"
try {
    $ppt = New-Object -ComObject PowerPoint.Application
    $pres = $ppt.Presentations.Open($pptx, [Microsoft.Office.Core.MsoTriState]::msoTrue, [Microsoft.Office.Core.MsoTriState]::msoFalse, [Microsoft.Office.Core.MsoTriState]::msoFalse)
    Write-Host "SUCCESS! Slides:" $pres.Slides.Count
    $pres.Close()
    $ppt.Quit()
} catch {
    Write-Host "FAILED AS EXPECTED:" $_.Exception.Message
}
