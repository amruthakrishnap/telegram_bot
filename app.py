from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, ContextTypes, MessageHandler, filters
from supabase import create_client, Client
import os
from telegram import ReplyKeyboardRemove, error

# Supabase Credentials
SUPABASE_URL = 'https://vjgxtqqrbehmoqsgorvq.supabase.co'
SUPABASE_KEY = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6InZqZ3h0cXFyYmVobW9xc2dvcnZxIiwicm9sZSI6ImFub24iLCJpYXQiOjE3MjI4NTI5ODcsImV4cCI6MjAzODQyODk4N30.Qlhws14rMtrM7frgxLKgM6flg3I1JvJ-JPd5gd6A3-Q'

# Initialize Supabase Client
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Store user responses
USER_RESPONSES = {}

# Welcome messages
WELCOME_MESSAGES = {
    "English": """👋 Welcome to our Busi.VIP channel, where deals don’t annoy you!...

💰 Discounts **greater than 30%**.
⭐ Products with **4-star ratings or higher**.
🛒 Verified **positive reviews from Amazon**.

**Before we start, we need to know a little more about what you're looking for:**""",
    "Spanish": """👋 ¡Bienvenido/a a nuestro canal Busi.VIP, donde las ofertas no te molestan!...

💰 Descuentos superiores al 30%.
⭐ Productos con **una calificación de 4 estrellas o más**.
🛒 Opiniones verificadas y positivas de Amazon.

**Antes de empezar, necesitamos saber un poco más sobre lo que buscas:**"""
}

# Questions
QUESTIONS = {
    "English": [
        {"question": "Who is the clothing for? You can select multiple options.",
         "options": ["Men", "Women", "Kids", "All options"], "key": "gender"},
        {"question": "What type of clothing are you looking for? You can select multiple options.",
         "options": ["T-shirts", "Pants", "Sweatshirts", "Sneakers", "Sandals", "All options"], "key": "clothing_type"},
        {"question": "What is your shoe size?",
         "options": [str(i) for i in range(18, 31)] + ["All options"], "key": "shoe_size"},
        {"question": "What is your clothing size?",
         "options": ["XS", "S", "M", "L", "XL", "XXL", "All options"], "key": "clothing_size"},
        {"question": "Do you have a preferred brand?",
         "options": ["Nike", "Adidas", "Puma", "No preference", "All options"], "key": "brand"}
    ]
}


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Start command to ask for language selection."""
    keyboard = [[InlineKeyboardButton("English", callback_data='English'),
                 InlineKeyboardButton("Español", callback_data='Spanish')]]
    reply_markup = InlineKeyboardMarkup(keyboard)

    await update.message.reply_text("Please select your language / Por favor, selecciona tu idioma:", reply_markup=reply_markup)


async def select_language(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle language selection and send welcome message."""
    query = update.callback_query
    await query.answer()

    selected_language = query.data
    context.user_data['language'] = selected_language
    USER_RESPONSES[query.from_user.id] = {}

    # ✅ Send welcome message as a **new message**
    await query.message.reply_text(WELCOME_MESSAGES[selected_language])

    # ✅ Start asking questions in a **new message**
    await ask_question(update, context, 0, new_message=True)


async def ask_question(update: Update, context: ContextTypes.DEFAULT_TYPE, step: int, new_message=False) -> None:
    """Ask a question based on the current step."""
    query = update.callback_query
    user_id = query.from_user.id
    language = context.user_data['language']

    if step >= len(QUESTIONS[language]):
        await store_preferences(user_id)
        await show_summary(update, context, user_id)
        return

    context.user_data['current_step'] = step
    question = QUESTIONS[language][step]
    key = question["key"]

    # ✅ Get selected clothing type
    clothing_type_selected = USER_RESPONSES[user_id].get("clothing_type", [])

    # ✅ Case 1: Skip Shoe Size if only clothing is selected
    if key == "shoe_size" and all(item in ["T-shirts", "Pants", "Sweatshirts"] for item in clothing_type_selected):
        await ask_question(update, context, step + 1)
        return

    # ✅ Case 2: Skip Clothing Size if only footwear is selected
    if key == "clothing_size" and all(item in ["Sneakers", "Sandals"] for item in clothing_type_selected):
        await ask_question(update, context, step + 1)
        return

    # ✅ Case 3: If "All options" is selected, ask both shoe and clothing size
    if "All options" in clothing_type_selected:
        pass  # Don't skip any question, ask both sizes

    # ✅ Case 4: If the user selects both clothing and footwear, ask both sizes
    if key == "shoe_size" and any(item in clothing_type_selected for item in ["Sneakers", "Sandals"]) and \
            any(item in clothing_type_selected for item in ["T-shirts", "Pants", "Sweatshirts"]):
        pass  # Ask shoe size normally

    if key == "clothing_size" and any(item in clothing_type_selected for item in ["T-shirts", "Pants", "Sweatshirts"]) and \
            any(item in clothing_type_selected for item in ["Sneakers", "Sandals"]):
        pass  # Ask clothing size normally

    # ✅ Create inline keyboard buttons
    keyboard = [[InlineKeyboardButton(f"{'✅' if option in USER_RESPONSES.get(user_id, {}).get(key, []) else ''} {option}",
                                      callback_data=f"{key}:{option}")]
                for option in question['options']]

    navigation_buttons = []
    if step > 0:
        navigation_buttons.append(InlineKeyboardButton("⬅ Back", callback_data="back"))
    navigation_buttons.append(InlineKeyboardButton("Next ➡", callback_data="next"))

    keyboard.append(navigation_buttons)
    reply_markup = InlineKeyboardMarkup(keyboard)

    # ✅ If it's the first question, send as a new message
    if new_message:
        await query.message.reply_text(text=question['question'], reply_markup=reply_markup)
    else:
        # ✅ Prevents "Message is not modified" error
        try:
            await query.message.edit_text(text=question['question'], reply_markup=reply_markup)
        except error.BadRequest as e:
            if "Message is not modified" not in str(e):
                raise e


async def handle_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle user responses, back, and next buttons."""
    query = update.callback_query
    await query.answer()

    user_id = query.from_user.id
    data = query.data

    if data == "next":
        step = context.user_data.get('current_step', 0) + 1
        await ask_question(update, context, step)
        return
    
    if data == "back":
        step = max(0, context.user_data.get('current_step', 0) - 1)
        await ask_question(update, context, step)
        return

    key, value = data.split(":")

    if user_id not in USER_RESPONSES:
        USER_RESPONSES[user_id] = {}

    if key not in USER_RESPONSES[user_id]:
        USER_RESPONSES[user_id][key] = []

    if value in ["All options"]:
        USER_RESPONSES[user_id][key] = QUESTIONS[context.user_data["language"]][context.user_data.get('current_step', 0)]["options"][:-1]
    else:
        if value in USER_RESPONSES[user_id][key]:
            USER_RESPONSES[user_id][key].remove(value)
        else:
            USER_RESPONSES[user_id][key].append(value)

    await ask_question(update, context, context.user_data.get('current_step', 0))


async def store_preferences(user_id: int):
    """Store user preferences in Supabase, merging clothing and shoe sizes into a single 'size' column."""
    if user_id in USER_RESPONSES:
        gender = USER_RESPONSES[user_id].get("gender", [])
        clothing_type = USER_RESPONSES[user_id].get("clothing_type", [])
        clothing_size = USER_RESPONSES[user_id].get("clothing_size", [])  # Clothing sizes like XS, S, M
        shoe_size = USER_RESPONSES[user_id].get("shoe_size", [])  # Shoe sizes like 18, 19, 20

        # ✅ Merge both clothing and shoe sizes into a single `size` column
        combined_size = clothing_size + shoe_size

        # ✅ Combine all selected values into `keywords`
        keywords = gender + clothing_type + combined_size + USER_RESPONSES[user_id].get("brand", [])

        data = {
            "user_id": user_id,
            "gender": gender,
            "clothing_type": clothing_type,
            "size": combined_size,  # ✅ Single `size` column storing both clothing and shoe sizes
            "brand": USER_RESPONSES[user_id].get("brand", []),
            "keywords": keywords  # ✅ Keywords include everything
        }

        # Insert or update existing record in Supabase
        response = supabase.table("user_product_preference").upsert(data, on_conflict=["user_id"]).execute()
        print("✅ Supabase Response:", response)

async def show_summary(update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int) -> None:
    query = update.callback_query
    responses = USER_RESPONSES.get(user_id, {})

    summary = "Perfect! You have selected:\n\n" if context.user_data['language'] == "English" else "Perfecto! Has seleccionado:\n\n"
    
    for key, values in responses.items():
        summary += f"{key.replace('_', ' ').title()}: {', '.join(values)}\n"

    summary += "\nThank you! We will find the best deals for you and send them soon. 🚀" \
        if context.user_data['language'] == "English" else "\n¡Gracias! Buscaremos las mejores ofertas para ti y te las enviaremos pronto. 🚀"

    # Send summary and explicitly remove the reply keyboard to prevent the extra button
    await query.message.edit_text(text=summary, reply_markup=None)
    await context.bot.send_message(chat_id=user_id, text="✅ Preferences saved successfully!", reply_markup=ReplyKeyboardRemove())

    # Clear stored user responses
    USER_RESPONSES.pop(user_id, None)

async def handle_check_deals(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Fetch and display top 5 matching products using direct filtering."""
    
    user_id = None
    query = None
    if update.callback_query:
        query = update.callback_query
        user_id = query.from_user.id
        await query.answer()
    elif update.message:
        user_id = update.message.from_user.id
    
    if not user_id:
        return

    # ✅ Fetch user preferences from Supabase
    user_response = supabase.table("user_product_preference").select(
        "gender, clothing_type, size, brand"
    ).eq("user_id", user_id).execute()

    user_data = user_response.data

    if not user_data:
        message_target = query.message if query else update.message
        if message_target:
            await message_target.reply_text("⚠️ No preferences found! Please set your preferences first.")
        return

    user_prefs = user_data[0]
    gender = user_prefs.get("gender", [])
    clothing_type = user_prefs.get("clothing_type", [])
    sizes = user_prefs.get("size", [])
    brands = user_prefs.get("brand", [])

    # ✅ Remove brand filter if "No Preference" is selected
    if "No preference" in brands:
        brands = []

    # ✅ Fetch all products from Supabase
    response = supabase.table("product_inventory").select(
        "title, image_cdn, current, average_price, discount_percentage, amazon_url, brand, product_type, category_tree, size"
    ).execute()

    product_data = response.data if response.data else []

    if not product_data:
        message_target = query.message if query else update.message
        if message_target:
            await message_target.reply_text("❌ No products found in inventory.")
        return

    # ✅ Filter by Brand
    if brands:
        product_data = [
            product for product in product_data if product["brand"].lower() in [b.lower() for b in brands]
        ]

    # ✅ Filter by Clothing Type (Product Type)
    if clothing_type:
        product_data = [
            product for product in product_data if product["product_type"].lower() in [ct.lower() for ct in clothing_type]
        ]
    
    # ✅ Filter by Gender (Category Tree in Spanish)
    gender_mapping = {
        "Hombre": "Men",
        "Mujer": "Women",
        "Niños": "Kids"
    }
    if gender:
        product_data = [
            product for product in product_data if any(
                gender_mapping.get(cat, cat) in gender for cat in product["category_tree"]
            )
        ]
    
    # ✅ Filter by Size
    if sizes:
        product_data = [
            product for product in product_data if product["size"].lower() in [s.lower() for s in sizes]
        ]

    if not product_data:
        message_target = query.message if query else update.message
        if message_target:
            await message_target.reply_text("❌ No matching products found for your preferences.")
        return

    # ✅ Sort by Discount Percentage (Descending)
    product_data = sorted(product_data, key=lambda x: x.get("discount_percentage", 0), reverse=True)[:5]

    for product in product_data:
        image_urls = product.get("image_cdn", "").split(",")  # Assuming multiple images are comma-separated
        title = product.get("title", "No Title")
        current_price = product.get("current", "N/A")
        average_price = product.get("average_price", "N/A")
        discount = product.get("discount_percentage", 0)
        amazon_url = product.get("amazon_url", "#")

        caption = (
            f"🛍 **{title}**\n"
            f"💰 *Current Price:* ${current_price}\n"
            f"📉 *Avg Price:* ${average_price}\n"
            f"🔥 *Discount:* {discount}%\n"
            f"🔗 [Buy on Amazon]({amazon_url})"
        )

        # ✅ Send the first image with the caption
        if image_urls:
            await context.bot.send_photo(chat_id=user_id, photo=image_urls[0], caption=caption, parse_mode="Markdown")

        # ✅ Send additional images without a caption
        for image_url in image_urls[1:]:
            await context.bot.send_photo(chat_id=user_id, photo=image_url)

# Main function
def main():
    app = Application.builder().token("7935005367:AAFHVTV1EzzWpbWaZhjx50pS-rdr1YphvhU").build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("check_deals", handle_check_deals))
    app.add_handler(CallbackQueryHandler(select_language, pattern="^(English|Spanish)$"))
    app.add_handler(CallbackQueryHandler(handle_response))
    app.add_handler(CallbackQueryHandler(handle_check_deals, pattern="^check_deals$"))

    app.run_polling()

if __name__ == '__main__':
    main()
