# Auto-hébergement du modèle de langage (souveraineté)

Xam-Xam peut utiliser n'importe quel serveur exposant l'**API compatible OpenAI**
(`/v1/chat/completions`) avec entrée image : **vLLM** (recommandé sur GPU) ou **Ollama**. Les
photos et transcriptions ne quittent alors pas votre infrastructure (hors Kiriku et WhatsApp,
voir la mention de confidentialité du README).

## 1. Choisir le modèle

Le modèle doit figurer dans la liste blanche (`provider: selfhosted`) de
[`modeles_autorises.json`](../src/xamxam/llm/modeles_autorises.json) ; licences et alternatives
dans [modeles.md](modeles.md). Points de départ :

| Modèle | Usage conseillé |
| --- | --- |
| `Qwen/Qwen3-VL-8B-Instruct` | premier essai sur un seul GPU |
| `mistralai/Ministral-3-8B-Instruct-2512` | même gabarit, autre famille, utile pour comparer |
| `mistralai/Ministral-3-14B-Instruct-2512`, `Qwen/Qwen3-VL-32B-Instruct`, `google/gemma-4-31B-it` | plus précis, GPU plus gros |

Ordre de grandeur de la mémoire GPU, poids en BF16 seulement (2 octets par paramètre) : environ
16 Go pour un modèle 8B, 28 Go pour 14B, 62 à 64 Go pour 31B-32B, **plus** le cache de contexte et
l'encodeur d'images. Un GPU de 24 Go suffit en principe pour un 8B avec un contexte réduit ; les
besoins exacts sont **à vérifier** sur votre matériel (ou avec une version quantifiée).

## 2. Lancer vLLM sur un GPU

Prérequis : GPU NVIDIA, pilotes et [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/install-guide.html), Docker.

```bash
# Clé d'accès au serveur, générée localement et à conserver comme un secret
export VLLM_API_KEY="$(openssl rand -hex 32)"

docker run --gpus all --ipc=host -p 8000:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  vllm/vllm-openai:<version> \
  --model Qwen/Qwen3-VL-8B-Instruct \
  --api-key "$VLLM_API_KEY" \
  --max-model-len 16384 \
  --limit-mm-per-prompt '{"image": 1}'
```

- Fixez une **version précise** de l'image (`<version>`) plutôt que `latest`. La syntaxe de
  certaines options (dont `--limit-mm-per-prompt`) a changé entre versions de vLLM : **à
  vérifier** dans la documentation de la version choisie.
- Le nom servi est l'identifiant du dépôt (`Qwen/Qwen3-VL-8B-Instruct`), celui attendu par la
  liste blanche. Ne le changez pas avec `--served-model-name`.
- Xam-Xam envoie `response_format` de type `json_schema` : vLLM l'applique par décodage guidé,
  ce qui donne un JSON conforme dès le premier essai.

Vérification :

```bash
curl -s http://localhost:8000/v1/models -H "Authorization: Bearer $VLLM_API_KEY"
```

### Alternative : Ollama

Ollama expose aussi une API compatible OpenAI sur `http://<hôte>:11434/v1`. Les noms de modèles
Ollama (étiquettes) diffèrent des identifiants Hugging Face : il faudrait ajouter l'étiquette
exacte à la liste blanche, après vérification de la licence du modèle empaqueté. Prise en charge
des images et de `response_format` par le modèle choisi : **à vérifier**.

## 3. Brancher Xam-Xam

```bash
LLM_PROVIDER=selfhosted
SELFHOSTED_BASE_URL=http://<hôte>:8000/v1
SELFHOSTED_MODEL=Qwen/Qwen3-VL-8B-Instruct
SELFHOSTED_API_KEY=<valeur de VLLM_API_KEY>   # optionnelle si le serveur n'en demande pas
```

Sur l'instance AWS, ces valeurs vont dans SSM sous `/xamxam/` (`SELFHOSTED_API_KEY` en
**SecureString**), comme les autres paramètres (voir [deploiement-aws.md](deploiement-aws.md)).
Le security group de l'instance autorise toute sortie : il suffit que le serveur vLLM soit
joignable depuis elle.

Au démarrage, le bot vérifie que le modèle est dans la liste blanche ; `GET /health` affiche
ensuite `"llm": {"provider": "selfhosted", "model": "Qwen/Qwen3-VL-8B-Instruct"}`.

## 4. Sécurité du serveur

- Ne l'exposez **pas** directement sur Internet : réseau privé, VPN, ou reverse proxy HTTPS
  avec filtrage par adresse. Toujours une clé (`--api-key`).
- Les journaux de vLLM peuvent contenir les requêtes, donc des photos et transcriptions :
  réglez leur niveau de détail et leur durée de conservation en conséquence.

## 5. Évaluer avant d'adopter

Comparez le serveur auto-hébergé à Bedrock sur vos propres photos (imprimées et manuscrites) :

```bash
python -m xamxam.eval llm --photos data/eval/photos --configs configurations.json --repetitions 3
```

Pour un modèle auto-hébergé, le coût par requête dépend de votre GPU : renseignez dans
`configurations.json` un prix équivalent par million de jetons si vous voulez le comparer à
Bedrock. Détails dans [modeles.md](modeles.md#comparer-les-modèles).
