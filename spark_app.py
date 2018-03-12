# coding: utf-8


from pyspark import SparkConf, SparkContext
from pyspark.streaming import StreamingContext
from pyspark.sql import Row, SQLContext
import sys
import requests
from nltk.corpus import stopwords
import nltk
from nltk.tokenize import RegexpTokenizer

nltk.download('stopwords')


def aggregate_tags_count(new_values, total_sum):
    return sum(new_values) + (total_sum or 0)


def get_sql_context_instance(spark_context):
    if ('sqlContextSingletonInstance' not in globals()):
        globals()['sqlContextSingletonInstance'] = SQLContext(spark_context)
    return globals()['sqlContextSingletonInstance']


def process_rdd(time, rdd):
    print("----------- %s -----------" % str(time))
    try:
        try:
            # Get spark sql singleton context from the current context
            sql_context = get_sql_context_instance(rdd.context)
        except:
            e = sys.exc_info()[0]
            print("Error1: %s" % e)
        try:
            # convert the RDD to Row RDD
            row_rdd = rdd.map(lambda w: Row(hashtag=w[0], hashtag_count=w[1]))
        except:
            e = sys.exc_info()[0]
            print("Error2: %s" % e)
        try:
            # create a DF from the Row RDD
            hashtags_df = sql_context.createDataFrame(row_rdd)
        except:
            e = sys.exc_info()[0]
            print("Error3: %s" % e)
        try:
            # Register the dataframe as table
            hashtags_df.registerTempTable("hashtags")
        except:
            e = sys.exc_info()[0]
            print("Error4: %s" % e)
        try:
            # get the top 10 hashtags from the table using SQL and print them
            hashtag_counts_df = sql_context.sql(
                "select hashtag, hashtag_count from hashtags order by hashtag_count desc limit 10".format(hashtags_df))
            for x in hashtag_counts_df.collect():
                print(x)
            hashtag_counts_df.show(False)
        except:
            e = sys.exc_info()[0]
            print("Error5: %s" % e)
        try:
            # call this method to prepare top 10 hashtags DF and send them
            send_df_to_dashboard(hashtag_counts_df)
        except:
            e = sys.exc_info()[0]
            print("Error6: %s" % e)
    except:
        e = sys.exc_info()[0]
        print("ErrorAll: %s" % e)


def send_df_to_dashboard(df):
    # extract the hashtags from dataframe and convert them into array
    top_tags = [t.hashtag for t in df.select("hashtag").collect()]
    # extract the counts from dataframe and convert them into array
    tags_count = [p.hashtag_count for p in df.select("hashtag_count").collect()]
    # initialize and send the data through REST API
    url = 'http://localhost:5001/updateData'
    request_data = {'label': top_tags, 'data': tags_count}
    response = requests.post(url, data=request_data)


# create spark configuration
conf = SparkConf()
conf.setAppName("MastodonStreamApp")
# create spark context with the above configuration
sc = SparkContext(conf=conf)
sc.setLogLevel("ERROR")
# create the Streaming Context from the above spark context with interval size 4 seconds
ssc = StreamingContext(sc, 4)
# setting a checkpoint to allow RDD recovery
ssc.checkpoint("checkpoint_MastodonApp")
# read data from port 9009
dataStream = ssc.socketTextStream("localhost", 9009)

# split each tweet into words
# words = dataStream.flatMap(lambda line: line.split(" ")) #deprecated
tokenizer = RegexpTokenizer(r'\w+')
words = dataStream.flatMap(lambda line: tokenizer.tokenize(line))
# print(str(words))
# # filter the words to get only hashtags, then map each hashtag to be a pair of (hashtag,1)
# hashtags = words.filter(lambda w: '#' in w).map(lambda x: (x, 1))
# map each word to be a pair of (word,1)
stopwords_combined = stopwords.words('english') + stopwords.words('french') + stopwords.words('spanish')\
                                     + stopwords.words('german')
wordsc = words.filter(lambda w: w.lower() not in stopwords_combined).map(lambda x: (x, 1))
# adding the count of each hashtag to its last count
tags_totals = wordsc.updateStateByKey(aggregate_tags_count)
# do processing for each RDD generated in each interval
tags_totals.foreachRDD(process_rdd)
# start the streaming computation
ssc.start()
# wait for the streaming to finish
ssc.awaitTermination()



