from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash, request
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user, login_required
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy.orm import relationship, DeclarativeBase, Mapped, mapped_column
from sqlalchemy import Integer, String, Text
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm
from typing import List
import smtplib
from dotenv import load_dotenv
import os

load_dotenv()

app = Flask(__name__)
app.config['SECRET_KEY'] = os.getenv("FLASK_KEY")
ckeditor = CKEditor(app)
Bootstrap5(app)


# CREATE DATABASE
class Base(DeclarativeBase):
    pass


app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DB_URI", "sqlite:///posts.db")
db = SQLAlchemy(model_class=Base)
db.init_app(app)

login_manager = LoginManager()
login_manager.init_app(app)

gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)


@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)


# CONFIGURE TABLES
class BlogPost(db.Model):
    __tablename__ = "blog_posts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    title: Mapped[str] = mapped_column(String(250), unique=True, nullable=False)
    subtitle: Mapped[str] = mapped_column(String(250), nullable=False)
    date: Mapped[str] = mapped_column(String(250), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    img_url: Mapped[str] = mapped_column(String(250), nullable=False)
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    author: Mapped["User"] = relationship("User", back_populates="posts")
    comments: Mapped[List["Comment"]] = relationship(back_populates="parent_post")


# TODO: Create a User table for all your registered users.

class User(UserMixin, db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(100), unique=True)
    password: Mapped[str] = mapped_column(String(100))
    name: Mapped[str] = mapped_column(String(1000))
    posts: Mapped[List["BlogPost"]] = relationship(back_populates="author")
    comments: Mapped[List["Comment"]] = relationship(back_populates="comment_author")


class Comment(db.Model):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    author_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("users.id"))
    comment_author: Mapped["User"] = relationship("User", back_populates="comments")
    post_id: Mapped[int] = mapped_column(Integer, db.ForeignKey("blog_posts.id"))
    parent_post: Mapped["BlogPost"] = relationship("BlogPost", back_populates="comments")


with app.app_context():
    db.create_all()


# admin-only decorator
def admin_only(function):
    @wraps(function)
    def wrapper_function(*args, **kwargs):
        if current_user.get_id() != "1":
            return abort(403)
        return function(*args, **kwargs)

    return wrapper_function


# TODO: Use Werkzeug to hash the user's password when creating a new user.
@app.route('/register', methods=["POST", "GET"])
def register():
    new_form = RegisterForm()
    if new_form.validate_on_submit():
        result = db.session.execute(db.select(User).where(User.email == new_form.email.data))
        user = result.scalar_one_or_none()
        if user is None:
            new_user = User(
                email=new_form.email.data,
                name=new_form.name.data,
                password=generate_password_hash(new_form.password.data, "pbkdf2:sha256", salt_length=8)
            )
            db.session.add(new_user)
            db.session.commit()
            return redirect(url_for('get_all_posts'))
        else:
            flash("You have already signed up with that email, login instead")
            return redirect(url_for('login'))

    return render_template("register.html", form=new_form)


# TODO: Retrieve a user from the database based on their email. 
@app.route('/login', methods=["GET", "POST"])
def login():
    new_form = LoginForm()
    if new_form.validate_on_submit():
        result = db.session.execute(db.select(User).where(User.email == new_form.email.data))
        user = result.scalar_one_or_none()
        if user is not None:
            if check_password_hash(user.password, new_form.password.data):
                login_user(user)
                return redirect(url_for('get_all_posts'))
            else:
                flash("Password incorrect. Please try again")
                return redirect(url_for('login'))
        else:
            flash("This email does not exist. Please try again.")
            return redirect(url_for('login'))

    return render_template("login.html", form=new_form)


@app.route('/logout')
def logout():
    logout_user()
    return redirect(url_for('get_all_posts'))


@app.route('/')
def get_all_posts():
    result1 = db.session.execute(db.select(BlogPost))
    posts = result1.scalars().all()
    return render_template("index.html", all_posts=posts)


# TODO: Allow logged-in users to comment on posts
@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    requested_post = db.get_or_404(BlogPost, post_id)
    comment_form = CommentForm()
    if comment_form.validate_on_submit():
        if current_user.is_authenticated:
            comment = Comment(
                content=comment_form.comment.data,
                comment_author=current_user,
                parent_post=requested_post,
            )
            db.session.add(comment)
            db.session.commit()
        else:
            flash("You need to login or register to comment.")
            return redirect(url_for('login'))

    return render_template("post.html", post=requested_post, form=comment_form)


# TODO: Use a decorator so only an admin user can create a new post

@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    if form.validate_on_submit():
        img = form.img_url.data or url_for('static', filename='assets/img/read_bg.jpg')
        new_post = BlogPost(
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=img,
            author=current_user,
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form)


# TODO: Use a decorator so only an admin user can edit a post
@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = current_user
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True)


# TODO: Use a decorator so only an admin user can delete a post
@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html")


def send_mail(name, email, phone, message):
    mail_content = f"Subject: New Message\n\nName: {name}\nEmail: {email}\nPhone: {phone}\nmessage: {message}"

    with smtplib.SMTP(os.getenv("host"), 2525) as connection:
        connection.starttls()
        connection.login(user=os.getenv("uname"), password=os.getenv("password"))
        connection.sendmail(from_addr=os.getenv("from"),
                            to_addrs=os.getenv("to"),
                            msg=mail_content)
        print("Mail Sent")


@app.route('/contact', methods=["POST", "GET"])
def contact():
    if request.method == "POST":
        data = request.form
        send_mail(data["name"], data["email"], data["phone"], data["message"])
        return render_template("contact.html", msg_sent=True)
    return render_template("contact.html", msg_sent=False)


if __name__ == "__main__":
    app.run(debug=False)
