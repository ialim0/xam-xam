# Instantané du benchmark de 100 phrases

Capture locale du 8 octobre 2026. Voir [l'analyse](../../docs/resultats-100.md) et le [protocole](../../docs/benchmark.md). Les CSV sont des résultats textuels issus de phrases synthétiques ; licence [CC BY-SA 4.0](../../data/LICENSE).

| Fichier | Contenu |
| --- | --- |
| [`run_info.json`](run_info.json) | Paramètres enregistrés, statut du lexique et termes appliqués. |
| [`stt/transcriptions.csv`](stt/transcriptions.csv) | 300 textes envoyés au TTS, transcriptions STT, WER et chemins relatifs des WAV. |
| [`stt/termes.csv`](stt/termes.csv) | Occurrences et échecs de reconnaissance des termes cibles. |
| [`rapport/resume.md`](rapport/resume.md) | Tableaux agrégés. |
| [`rapport/classement_termes.csv`](rapport/classement_termes.csv) | Statistiques par terme. |
| [`rapport/formules_stt.csv`](rapport/formules_stt.csv) | Éléments de formule attendus et repérés. |
| [`rapport/diagnostic_phrases.csv`](rapport/diagnostic_phrases.csv) | 100 phrases classées pour l'écoute. |
| [`SHA256SUMS`](SHA256SUMS) | Empreintes des entrées et de cet instantané. |

Les chemins `audio/*.wav` dans les CSV désignent des audios **non inclus dans le dépôt**. Aucune évaluation humaine n'est publiée, car aucune n'a été réalisée. Les textes wolof et les prononciations évaluées sont au statut brouillon. Les transcriptions ont été obtenues avec les services Kiriku du challenge ; leur version exacte n'a pas été consignée. Le code du rapport correspondant est au commit `b4d35c9` ; le commit exact et les paramètres internes de génération des WAV ne sont pas consignés. Il n'est donc pas possible de reproduire le signal audio à l'identique à partir de cet instantané.

Depuis la racine du dépôt, les rapports peuvent être recalculés **sans API** :

```bash
python -m xamxam.eval report --output-dir results/benchmark-100
sha256sum -c results/benchmark-100/SHA256SUMS
```

La commande `report` recalcule les quatre fichiers de `rapport/` à partir des CSV `stt/` et de `run_info.json`. Le corpus et le lexique d'entrée sont dans [`data/`](../../data/) ; leurs empreintes figurent aussi dans `SHA256SUMS`. Pour refaire les appels TTS/STT, utilisez un autre dossier de sortie afin de conserver cet instantané.
