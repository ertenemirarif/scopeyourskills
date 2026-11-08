<p align="center"><img src="assets/logo-320.gif" alt="SkillScope logosu" width="160"></p>

# SkillScope

[English](README.md) · **Türkçe**

**Elimde hangi skill'ler var, ne işe yarıyorlar ve hangileri birbirinin alanına giriyor?**

Sosyal medyada önerilen skill repolarını indirmek kolay, ama bir süre sonra neyin kurulu olduğu, neyin işe yaradığı ve hangilerinin aynı işi yaptığı belirsizleşiyor. SkillScope bu karmaşayı düzenler. Bilgisayardaki tüm `SKILL.md` dosyalarını tarar ve skill'leri temaya ve pakete göre gruplar. Çakışan ve tekrar eden skill'leri işaretler. Sonucu internet gerektirmeyen tek bir HTML dashboard'da sunar.

Taranan yerler: Claude Code, Claude Desktop plugin'leri, Codex, Gemini/Antigravity ve belirtilen indirme klasörleri.

## Neler sunar

- **Keşfet:** Toplam, tekil, kurulu ve yalnızca indirilmiş skill sayıları ile temalara göre kurulum durumu. "Aktif çakışma" kutusu doğrudan çakışmalar sayfasına götürür.
- **Skill kataloğu:** Skill'ler önce kategoriye, sonra pakete göre gruplanır. Her paket başlığında paketin adı, yazarı, kısa açıklaması ve GitHub bağlantısı yer alır. Bir kategorinin satırları aynı bant rengini taşır; bir sonraki kategoriye geçildiğinde renk değişir.
- **Okunur adlar:** `bio-research:instrument-data-to-allotrope` gibi teknik adlar, satırda *Instrument Data to Allotrope* olarak görünür. Teknik ad ayrıntı panelinde durur.
- **Durum ve işlemler:** Her satırda *Kurulu*, *Başka yerde kurulu* ya da *Kurulu değil* etiketi bulunur.
  - **Aç:** Ayrıntı panelini açar. Panelde açıklama, kategori, kaynak, dosya konumları ve benzer skill'ler yer alır.
  - **Kur:** Hazır bir kurulum komutunu panoya kopyalar. Komut, skill'i `~/.claude/skills` klasörüne taşır. Sayfanın kendisi hiçbir dosyaya dokunmaz; komut terminalde çalıştırılır.
- **Yıldız ve lisans:** `--github` ile her paketin GitHub yıldız sayısı ve lisansı gösterilir. MIT yeşil renkte görünür. Ticari olmayan kullanım şartı taşıyan, kapalı ya da belirsiz lisanslar ayrıca vurgulanır. Lisans önce paketin kendi `LICENSE` dosyasından okunur. GitHub'daki bilgiyle uyuşmazsa yanında `*` işareti çıkar.
- **Repo karnesi:** İndirilen her repo için kaç skill'in zaten kurulu olduğunu, kaçının mevcut bir skill'le çakıştığını ve kaçının gerçekten yeni olduğunu gösterir. Bu sayede hangi reponun gerçekten katkı sağladığı tek bakışta anlaşılır.
- **Çakışmalar**, önem sırasına göre:
  - *Aktif çakışmalar:* Farklı paketlerden gelen, aynı araçta birlikte yüklü ve aynı işi tarif eden skill'ler. Bunlar aynı isteği karşılamak için yarışır.
  - *Aynı paket içi:* Birbirine benzeyen kardeş skill'ler. Çoğunlukla bilinçli bir tasarım tercihidir.
  - *İndirilen ↔ kurulu:* İndirilmiş bir skill, kurulu bir skill'in yaptığı işi tekrar eder.
  - *Aynı ad, farklı sürüm:* Hangisinin yüklendiği belirsiz olabilir.
  - *Birebir kopyalar:* İçeriği aynı olan dosyalar.
- **Dört dil:** Arayüz; Türkçe, İngilizce, Çince ve İspanyolca arasında, kenar çubuğundaki bayraklarla değiştirilir. Skill açıklamaları da *Orijinal* ile seçili dil arasında gösterilebilir.

## Claude skill'i olarak kullanım (önerilen)

Repo, kişisel skill klasörüne klonlanır:

```bash
git clone https://github.com/<kullanıcı>/skillscope.git ~/.claude/skills/skillscope
```

Ardından Claude'a *"skill envanterimi çıkar"* ya da *"run skillscope"* demek yeterlidir. Claude şunları kendisi yapar:

1. Skill'leri tarar.
2. Eksik açıklamaları Türkçe, İngilizce, Çince ve İspanyolcaya çevirir. Bunun için API anahtarı gerekmez.
3. Dashboard'u oluşturup açar.

Başka bir dil istendiğinde ("Almancasını da ekle" gibi), o dil de ayrıca hazırlanır. Adımların tamamı [SKILL.md](SKILL.md) dosyasında yer alır.

## Hızlı başlangıç (Claude olmadan)

Yalnızca Python 3.9 veya üstü gerekir; ek paket kurulmaz.

```bash
git clone https://github.com/<kullanıcı>/skillscope.git
cd skillscope
python skillscope.py --open
```

İndirilmiş repoların bulunduğu klasörler ayrıca eklenebilir. Bu klasörlerdeki skill'ler *kurulu değil* olarak sayılır:

```bash
python skillscope.py --path "İndirilenler=D:/repolar" --github --open
```

| Seçenek | Anlamı |
|---|---|
| `--path ETİKET=KLASÖR` | *İndirilmiş* olarak taranacak ek klasör (birden çok kez kullanılabilir) |
| `--active-path ETİKET=KLASÖR` | Claude'un yüklediği ek bir skill klasörü, ör. bir projenin `.claude/skills` klasörü |
| `--no-defaults` | Otomatik bulunan kurulum konumlarını atlar |
| `--threshold 0.25` | Çakışma için benzerlik eşiği (0-1). Yükseldikçe daha az ama daha güçlü eşleşme çıkar |
| `--lang tr` | Dashboard'un varsayılan dili |
| `--langs tr,en,zh,es` | Açıklama çevirisi hazırlanacak diller |
| `--github` | GitHub'dan yıldız ve lisans bilgisini çeker (`GITHUB_TOKEN` ya da `gh` oturumu kullanılır, 24 saat önbelleğe alınır) |
| `--export-missing KLASÖR` / `--merge DİL DOSYA` | Çevrilmemiş açıklamaları dile göre dışa aktarır; çevrilmiş dosyayı geri birleştirir |
| `--categories DOSYA` | Kendi tema kuralları |
| `--out KLASÖR` | Çıktı klasörü (varsayılan `output/`) |

Çıktı: `output/skillscope.html` ve `output/skills.json`.

## Çeviriler

Açıklaması zaten seçili dilde olan skill'ler olduğu gibi gösterilir. Diğerleri `translations/<dil>.json` önbelleğinden gelir. Bu önbellek üç yoldan doldurulabilir:

1. **Claude skill'i:** Önerilen yoldur. Claude eksikleri kendisi çevirir ve önbelleğe ekler.
2. **Claude API:** `ANTHROPIC_API_KEY=... python skillscope.py --translate` komutuyla eksikler çevrilip kaydedilir.
3. **Herhangi bir çevirmen:** `--export-missing` ile dışa aktarılan dosya çevrilir, `--merge` ile geri eklenir.

Önbellekte karşılığı olmayan açıklamalar için, tarayıcıda yerleşik çeviri desteği varsa (güncel masaüstü Chrome) çeviri cihaz üzerinde yapılır. Hâlâ çevrilmemiş metinler orijinal hâliyle, "çevrilmedi" işaretiyle gösterilir.

## Nasıl çalışır

- **Temalar:** [`categories.json`](categories.json) içindeki Türkçe ve İngilizce anahtar kelime kurallarıyla belirlenir. Skill adındaki eşleşmeler 3 kat ağırlık taşır. En yüksek puanı alan tema ana tema olur; ona yakın puan alanlar ikincil tema olarak eklenir. Dosya düzenlenerek yeni temalar tanımlanabilir.
- **Çakışmalar:** Her skill'in adı ve açıklaması üzerinden TF-IDF kosinüs benzerliği hesaplanır. Bu metin, ajanın hangi skill'i kullanacağına karar verirken okuduğu metindir. Bu yüzden açıklamaları benzeyen iki skill aynı isteğe aday olur. Aynı repodan gelen skill'ler için eşik biraz daha yüksek tutulur, çünkü kardeş skill'ler doğal olarak benzer kelimeler kullanır.
- **Kurulu ve indirilmiş ayrımı:** Otomatik bulunan konumlar kurulu sayılır. İndirilmiş bir skill'in aynı içeriği ya da adı başka bir yerde kuruluysa bu ayrıca belirtilir.

**Bilinen sınırlar:**

- Tema ataması anahtar kelimeye dayalı bir tahmindir. Bazı skill'ler *Diğer* başlığına ya da komşu bir temaya düşebilir.
- Benzerlik kelime düzeyindedir. Aynı işi çok farklı kelimelerle anlatan iki skill gözden kaçabilir.
- Okunur adlar otomatik üretilir ve zaman zaman kusurlu olabilir.

## Gizlilik

Tüm işlem yerelde yapılır. `--github` kullanıldığında GitHub'a yalnızca herkese açık repo adları gönderilir. Oluşan dashboard dosyası, bilgisayardaki dosya yollarını ve skill listesini içerir. Bu yüzden paylaşılmadan önce gözden geçirilmesi önerilir. `output/`, `translations/` ve `cache/` klasörleri git dışında tutulur.

## Testler

```bash
python -m unittest discover -s tests
```

## Lisans

MIT
