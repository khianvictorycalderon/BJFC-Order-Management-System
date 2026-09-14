# Bespren Johny's Fried Chicken Order Management System
Web Development (ITPS309) + Professional Elective 3 (PELEC304) Finals Project.

### Tech Stacks:
- Django
- HTML (via templates)
- Tailwind CSS (via CDN)
- JavaScript

### Prerequisites:
If you don't have the following, install it.
- Git *(CLI is recommended instead of GitHub Desktop)*
- Python *(Recommended version: 3.14 and above)*
- `pip` - *Usually comes installed along with Python if you checked the `install pip` box.*

---

### Group 3 Members:

#### Team Leader:
- [Khian Victory D. Calderon](https://github.com/khianvictorycalderon)

#### Figma Designers / Prototype Designers:
- [Alma Bautista](https://github.com/Bautista-mai) **(Figma Desginer Leader)**
- [Neftaly Careg](https://github.com/nftly2)
- [Cynon De Leon](https://github.com/Kieere)

#### Backend Developers / Database Engineers:
- [Sean Alonzo](https://github.com/Incineradia) **(Backend Developer Leader)**
- [Jonel Pronton](https://github.com/jnl06)
- [Kyla Heart Pineda](https://github.com/pkylaheart)
- [Karl Ibrahym Oabel](https://github.com/Oabelkarl123)

#### Frontned Designers / UI Designers
- [Ceejay Petalvero](https://github.com/Psyche0524) **(Frontend Designer Leader)**
- [John Marc De Villa](https://github.com/Jon-markus)
- [Geoffrey Dalumpienes](https://github.com/geofrmdatso)
- [Warren Tomo](https://github.com/renam0to)

#### Frontend Engineers / Data Engineer
- [Maureen Jane Urusa](https://github.com/mawi-ursua) **(Frontend Engineer Leaader)**
- [John Michael Mamac](https://github.com/JM17mc)
- [Nathaniel Esguerra](https://github.com/NielEsguerra)
- [Christian Lenard Melecia](https://github.com/lnrd01)

#### Documentation Team
- [Lester Genton](https://github.com/ReleasedDevil) **(Documentation Team Leader)**
- [James Walter Imperial](https://github.com/imperialjameswalter-BSIT3A)

---

### First Setup
Below are the steps you will do for first time setting up this project.
1. Clone this repository via `git clone https://github.com/khianvictorycalderon/BJFC-Order-Management-System.git`.
2. Create a virtual environment via `python -m venv venv`.
3. Activate the virtual environment via `venv\Scripts\activate`.
4. Before running any CLI command again, check your CLI, it should have a `(venv)` at the left side. For example: `(venv) D:\myproject\>`. If it has the `(venv)`, the virtual environment is already activated, if not, repeat step 3.
5. Using the CLI with virtual environment, install the necessary dependencies via `pip install -r requirements.txt`
6. Create an `.env` file in the root directory *(root directory means if you can see the `dj` folder, then it's the root directory, if not, click back to previous folder)*. The `.env` file should contain the following content:
    ```env
    DJANGO_ENV=...
    DJANGO_SECRET_KEY=...
    DEBUG=...
    ALLOWED_HOSTS=...
    ```
7. Replace all the ones with `...` with actual values. To get the values of the following:
    - `DJANGO_ENV` -> either `production` or `development` only. Since we are developing this project, the value should be `development`
    - `DJANGO_SECRET_KEY` -> Run this in any python interpreter and copy it's printed random character value:
        ```python
        from django.core.management.utils import get_random_secret_key
        print(get_random_secret_key())
        ```
    - `DEBUG` -> either `True` or `False` only, used to display useful information in development. Set this to `True` since we are in development, but it must be set to `False` on production.
    - `ALLOWED_HOSTS` -> this is the url where you want your django project to be hosted, for now just set this to `127.0.0.1, localhost`
8. Run `python manage.py migrate` to sync the Django models with the database schema.
9. Run the server via `python manage.py runserver`. *NOTE: If it showed an error related to something like `port used`, just used another port like `7000`, so the command would become something like `python manage.py runserver 7000`*.
10. You can code now!

### Admin Access
1. Create a superuser via `python manage.py createsuperuser`.
2. Fill out the necessary information being asked.
3. Go to `/admin` of your django url project and login.
4. Done!

### Pull Guide:

Meaning sync your local version of repository to the remote branch. *ANALOGY: Copying someone else's notes and writing to your own notebook.*

- Everytime you are about to edit or commit a file, run `git pull origin main` first. You should also run it if the Team Leader announced that there are changes in the remote main branch.
- Avoid pulling while you have unsaved files, or files you have saved but haven't committed it yet. Commit first, then pull.
- Always run `python manage.py migrate` for any changes in the models.

### Push Guide:

Meaning uploading the code you made for the whole team to see and use. *ANALOGY: You write in someone else's notebook by copying your own notes so that everyone can see it.*

1. Run `git add .` to add all files you have edited. *You can also commit a specific file like `git add ./data/sample.py` if you want to commit that file only and nothing else*.
2. Run `git commit -m "YOUR-COMMIT-MESSAGE"`. Replace the `YOUR-COMMIT-MESSAGE` with you actual commit message. Example: `git commit -m "Fixed navbar mobile unresponsiveness"`.

    **COMMIT MESSAGE NOTE**: Always make sure that your commit message is as detailed as possible, past tense, and clearly communicates to other developers of what you have done. As much as possible, minimum of 3 words.
    - Examples of **BAD COMMIT MESSAGE**:
        - `Updated frontend`
        - `Updated`
        - `Fixed`
    
        Because it does not clearly communicates to other developers what changed.

    - Examples of **GOOD COMMIT MESSAGE**:
        - `Updated source configuration data`
        - `Added navbar to all public pages`
        - `Added sidebar to a private layout`
        - `Changed color theme from orange to purple`
        - `Fixed navbar mobile responsiveness bug`

        Because it clearly communicates to other developers what you have done and what changed. Other developers can look at it at one glance and immediately know what changed.

3. After committing your changes, push your changes to the remote branch via `git push origin main:YOUR-REMOTE-BRANCH`. DO NOT PUSH to the main branch like `git push origin main`. You should have the colon `:`. Now what does that mean? When you push with just `main`, it tells git to push from my local `main` branch to the remote `main` branch. But when you do something like `main:pages/public/ui`, it tells git that from my local `main` branch, push it to remote's `pages/public/ui` branch, so that way you don't push to the remote main branch. **BECAUSE LOCAL BRANCH AND REMOTE BRANCH ARE DIFFERENT**. Now when it comes to naming the branch you want to push, it's better to use a `/` and what that changed is all about. For example, you and your team changed something in the public page's navigation bar, then your remote branch should be `pages/public/navbar`. If you added a notification feature for example, the remote branch name should be `feature/notification` since you added a notification feature to the project. For consistency, minimum of 1 slash `/` for any remote branch name. It's up to you how you would name it. You should also name it as clearly and detailed as possible like the commit message stated above.
4. Done!

### NOTES FOR MEMBERS:
- All tasks are posted on our github repo's issues, check the boxes once you finished the tasks assigned to you..
- If you encountered an error, always read first the error message first, then search how to fix it, or use AI. If it still doesn't work, then you can ask in our GC what's the solution.
- For backend developers, always run `python manage.py makemigrations` if you changed something in the models.