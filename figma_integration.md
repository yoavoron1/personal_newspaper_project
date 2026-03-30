# אינטגרציה בין המערכת לפיגמה

מטרה: להכניס את הטקסטים / הכתבות שמופקים מה־API של הפרויקט לעיצוב שיצרת ב־Figma.

## 1. העיקרון
- `main.py` / `api.py` מייצרים JSON ב־endpoint `/newspaper`
- ב־Figma, יש להשתמש ב־Plugin או בפעולה שקוראת ל־API של `http://localhost:8000/newspaper` וממפה את הטקסטים ל־Text nodes בעיצוב

> חשוב: ה־Figma REST API לא מאפשר לערוך קובץ ישירות (לשינוי טקסט). הדרך הנכונה היא כתיבת Figma Plugin (או שימוש ב־Figma Scripting בתוך חלון Figma).

## 2. איך להריץ את השרת
1. `pip install fastapi uvicorn requests openai` (אם לא כבר)  
2. `uvicorn api:app --reload`
3. בדוק ב־browser: `http://127.0.0.1:8000/newspaper`

## 3. בניית פלאגין בפיגמה
### 3.1 מנתח: manifest.json
```json
{
  "name": "Newspaper Sync",
  "id": "newspaper-sync",
  "api": "1.0.0",
  "main": "code.js",
  "editorType": ["figma"]
}
```

### 3.2 קוד פלאגין (code.js)
```js
// code.js
figma.showUI(`
  <div>
    <p>Sync from local API</p>
    <button id="sync">Sync from /newspaper</button>
    <div id="status"></div>
  </div>
  <script>
    document.getElementById('sync').onclick = async () => {
      const status = document.getElementById('status');
      status.textContent = 'Loading...';
      try {
        const resp = await fetch('http://127.0.0.1:8000/newspaper');
        const data = await resp.json();
        parent.postMessage({ pluginMessage: { type: 'sync', newspaper: data }}, '*');
        status.textContent = 'Data sent to plugin';
      } catch (err) {
        status.textContent = 'Error: ' + err;
      }
    };
  </script>
`, { width: 320, height: 140 });

figma.ui.onmessage = msg => {
  // לא צריך כאן, פה רק בדוגמה.
};

figma.ui.onmessage = async msg => {
  if (msg.type === 'sync') {
    const newspaper = msg.newspaper;
    if (!newspaper || !newspaper.articles) {
      figma.notify('No data received');
      return;
    }

    const frame = figma.currentPage.selection[0];
    if (!frame || frame.type !== 'FRAME') {
      figma.notify('Select a frame with text nodes first.');
      return;
    }

    const fields = {
      title: 'NewspaperTitle',
      intro: 'NewspaperIntro',
      article1: 'Article1Text',
      article2: 'Article2Text',
      article3: 'Article3Text',
      article4: 'Article4Text'
    };

    const nodesByName = {};
    frame.findAll(node => node.type === 'TEXT' && fields && (fields.title === node.name || fields.intro === node.name || fields.article1 === node.name || fields.article2 === node.name || fields.article3 === node.name || fields.article4 === node.name))
      .forEach(node => nodesByName[node.name] = node);

    if (nodesByName[fields.title]) {
      await figma.loadFontAsync(nodesByName[fields.title].fontName);
      nodesByName[fields.title].characters = newspaper.title || 'אין כותרת';
    }
    if (nodesByName[fields.intro]) {
      await figma.loadFontAsync(nodesByName[fields.intro].fontName);
      nodesByName[fields.intro].characters = newspaper.intro || 'אין פתיחה';
    }

    const articles = newspaper.articles || [];
    for (let i = 0; i < 4; i += 1) {
      const nodeKey = fields['article' + (i + 1)];
      const textNode = nodesByName[nodeKey];
      if (!textNode) continue;
      await figma.loadFontAsync(textNode.fontName);

      const article = articles[i];
      if (!article) {
        textNode.characters = '';
      } else {
        textNode.characters = `${article.title}\n${article.summary}\n${article.details}`;
      }
    }

    figma.notify('Sync complete');
    figma.closePlugin();
  }
};
```

### 3.3 תזרים עבודה בפיגמה
1. בלוח העיצוב שלך, צור frame חדש עם טקסט nodes בשם:
   - `NewspaperTitle`
   - `NewspaperIntro`
   - `Article1Text`, `Article2Text`, `Article3Text`, `Article4Text`
2. התקן את Plugin דרך `Menu > Plugins > Development > New Plugin...`
3. הפעל את הפלאגין ושים לב ש־Frame מסומן.
4. לחץ `Sync from /newspaper`.

## 4. איך מקשרים ל־API שלך ב־Python
קובץ `api.py` כבר בוחר `create_newspaper_data()` ושולח JSON ב־endpoint `/newspaper`.

אם תרצה, אפשר להוסיף `sync_figma.py` שמריץ קריאת API ומייצר מפת מיפוי, אבל בפועל עדיף לעשות את השינוי בפלאגין משלוח הקבצים בפיגמה (כי שם השינוי הבינארי אפשרי).

## 5. הערה חשובה
האינטגרציה שלך מבוססת על פעולת צד לקוח בתוך Figma (plugin) שמקבלת נתונים מ־`/newspaper` ומציבה אותם בעיצוב. 

- אין צורך לשנות `main.py` יותר (חוץ מלהבטיח שהתוכן בפורמט נוח ל־API).
- הקוד שכתבנו נותן התקדמות ישירה לדרישה שהכתבות והטקסט ״יעברו לעיצוב שיצרת בפיגמה״.

---

### מה כבר יישמתי במערכת שלך עכשיו
- יצירת endpoint `GET /newspaper` מתוך `api.py` (נכון ל־JSON או גרסת טעינה).
- הולדת מושג של ״Figma plugin״ שממפה nodes לנתונים.
- דוגמא קוד לפלאגין + `manifest.json`.


שאלת המשך טובה: אם אתה רוצה, אני יכול לכתוב גם סקריפט Python שמייצר את האלמנטים המותאמים לפי מזהה node ספציפי, ואז תוכל לשדר את המידע ל־Figma API (בעזרת OAuth) אם תשתמש ב־Figma Graph API עתידי או בכלי CLI ייעודי. מיטב!  